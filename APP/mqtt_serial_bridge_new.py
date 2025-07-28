#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BJG移动平台控制系统 - MQTT到串口桥接程序
功能：接收来自网页的MQTT命令，通过串口转发给STM32
支持自动串口检测和选择
"""

import paho.mqtt.client as mqtt
import serial
import serial.tools.list_ports
import time
import json
import logging
from datetime import datetime
import threading
import queue
import platform
import os

class MQTTSerialBridge:
    def __init__(self, mqtt_broker="10.246.223.221", mqtt_port=7000, 
                 serial_port=None, serial_baudrate=115200):
        """
        初始化MQTT串口桥接器
        """
        self.mqtt_broker = mqtt_broker
        self.mqtt_port = mqtt_port
        self.serial_port = serial_port
        self.serial_baudrate = serial_baudrate
        
        # 初始化组件
        self.mqtt_client = None
        self.serial_conn = None
        self.command_queue = queue.Queue()
        self.running = False
        
        # 设置日志
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('bjg_control.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        
        # MQTT主题配置
        self.water_topic = "bjg/control/water"
        self.track_topic = "bjg/control/track"
        self.unlock_topic = "bjg/control/unlock"
        
    def scan_serial_ports(self):
        """扫描可用的串口"""
        ports = serial.tools.list_ports.comports()
        available_ports = []
        
        print("🔍 正在扫描可用串口...")
        
        for port in ports:
            port_device = port.device.lower()
            port_desc = str(port.description).lower() if port.description else ""
            
            # Linux下的设备识别
            if platform.system() == "Linux":
                # 过滤掉虚拟设备
                if any(skip in port_device for skip in ['bluetooth', 'virtual', 'pty']):
                    continue
                
                # 常见的STM32/Arduino设备
                if any(keyword in port_device for keyword in ['/dev/ttyusb', '/dev/ttyacm', '/dev/ttyserial']):
                    available_ports.append(port)
                    print(f"  📱 找到USB串口: {port.device}")
                elif any(keyword in port_desc for keyword in ['stm32', 'stlink', 'arduino', 'ch340', 'cp210', 'ftdi']):
                    available_ports.append(port)
                    print(f"  🎯 找到可能的STM32设备: {port.device}")
                elif 'usb' in port_desc and 'serial' in port_desc:
                    available_ports.append(port)
                    print(f"  🔌 找到USB串口设备: {port.device}")
                    
            elif platform.system() == "Windows":
                # Windows下的COM端口
                if port.device.startswith('COM'):
                    # 过滤虚拟端口
                    if 'virtual' not in port_desc:
                        available_ports.append(port)
                        if any(keyword in port_desc for keyword in ['stm32', 'stlink', 'arduino', 'ch340', 'cp210', 'ftdi']):
                            print(f"  🎯 找到可能的STM32设备: {port.device}")
                        else:
                            print(f"  📱 找到COM端口: {port.device}")
            else:
                # 其他系统（macOS等）
                available_ports.append(port)
        
        if not available_ports:
            print("❌ 未发现可用的串口设备")
            print("\n故障排除建议:")
            print("  1. 检查STM32设备是否已正确连接到计算机")
            print("  2. 检查USB驱动程序是否已安装")
            if platform.system() == "Linux":
                print("  3. 检查当前用户权限:")
                print("     sudo usermod -a -G dialout $USER")
                print("     然后重新登录")
                print("  4. 检查设备文件权限:")
                print("     ls -l /dev/ttyUSB* /dev/ttyACM*")
            print("  5. 确认设备未被其他程序占用")
        else:
            print(f"✅ 总共发现 {len(available_ports)} 个可用串口")
        
        return available_ports
    
    def select_serial_port(self):
        """选择串口"""
        if self.serial_port:
            # 如果已指定串口，直接使用
            print(f"✅ 使用指定的串口: {self.serial_port}")
            return self.serial_port
        
        print("\n" + "="*60)
        print("🔍 BJG移动平台 - 串口检测与选择")
        print("="*60)
        
        available_ports = self.scan_serial_ports()
        
        if not available_ports:
            return None
        
        if len(available_ports) == 1:
            # 只有一个串口，自动选择
            selected_port = available_ports[0]
            print(f"\n✅ 自动选择唯一可用串口:")
            print(f"   端口: {selected_port.device}")
            print(f"   描述: {selected_port.description}")
            if hasattr(selected_port, 'manufacturer') and selected_port.manufacturer:
                print(f"   制造商: {selected_port.manufacturer}")
            if hasattr(selected_port, 'vid') and hasattr(selected_port, 'pid') and selected_port.vid and selected_port.pid:
                print(f"   VID:PID = {selected_port.vid:04X}:{selected_port.pid:04X}")
            return selected_port.device
        
        # 多个串口，让用户选择
        print(f"\n📋 发现 {len(available_ports)} 个可用串口，请选择:")
        print("-" * 80)
        
        # 按类型排序，STM32相关的排在前面
        def port_priority(port):
            desc = str(port.description).lower() if port.description else ""
            if any(keyword in desc for keyword in ['stm32', 'stlink']):
                return 0  # 最高优先级
            elif any(keyword in desc for keyword in ['arduino', 'ch340', 'cp210', 'ftdi']):
                return 1  # 第二优先级
            else:
                return 2  # 普通优先级
        
        available_ports.sort(key=port_priority)
        
        for i, port in enumerate(available_ports, 1):
            print(f"{i:2d}. 端口: {port.device}")
            print(f"     描述: {port.description}")
            if hasattr(port, 'manufacturer') and port.manufacturer:
                print(f"     制造商: {port.manufacturer}")
            if hasattr(port, 'vid') and hasattr(port, 'pid') and port.vid and port.pid:
                print(f"     VID:PID = {port.vid:04X}:{port.pid:04X}")
            
            # 标记推荐的端口
            desc = str(port.description).lower() if port.description else ""
            if any(keyword in desc for keyword in ['stm32', 'stlink']):
                print(f"     ⭐ 推荐：这很可能是STM32设备")
            elif any(keyword in desc for keyword in ['arduino']):
                print(f"     💡 提示：这是Arduino兼容设备")
                
            print()
        
        print("=" * 80)
        
        while True:
            try:
                choice = input("🎯 请选择串口 (输入序号1-{}, 或按q退出): ".format(len(available_ports))).strip()
                
                if choice.lower() in ['q', 'quit', 'exit']:
                    print("❌ 用户取消选择")
                    return None
                
                if choice.isdigit():
                    index = int(choice) - 1
                    if 0 <= index < len(available_ports):
                        selected_port = available_ports[index]
                        print(f"\n✅ 已选择串口: {selected_port.device}")
                        print(f"   描述: {selected_port.description}")
                        return selected_port.device
                    else:
                        print(f"❌ 无效的序号，请输入1-{len(available_ports)}之间的数字")
                else:
                    print("❌ 请输入数字序号或按q退出")
                    
            except KeyboardInterrupt:
                print("\n❌ 用户中断操作")
                return None
            except Exception as e:
                print(f"❌ 输入错误: {e}")
                print("请重新输入")
    
    def test_serial_connection(self, port):
        """测试串口连接"""
        try:
            test_conn = serial.Serial(
                port=port,
                baudrate=self.serial_baudrate,
                timeout=2,
                write_timeout=2
            )
            time.sleep(1)  # 等待连接稳定
            
            # 发送测试命令
            test_conn.write(b"WS")  # 发送停止命令
            test_conn.flush()
            
            # 尝试读取响应
            time.sleep(0.5)
            if test_conn.in_waiting > 0:
                response = test_conn.read(test_conn.in_waiting).decode('utf-8', errors='ignore')
                if response.strip():
                    print(f"✅ 设备响应: {response.strip()}")
            
            test_conn.close()
            return True
            
        except Exception as e:
            self.logger.warning(f"串口测试失败 {port}: {e}")
            return False
        
    def init_mqtt(self):
        """初始化MQTT客户端"""
        try:
            self.mqtt_client = mqtt.Client()
            self.mqtt_client.on_connect = self.on_mqtt_connect
            self.mqtt_client.on_message = self.on_mqtt_message
            self.mqtt_client.on_disconnect = self.on_mqtt_disconnect
            
            self.logger.info(f"正在连接MQTT代理: {self.mqtt_broker}:{self.mqtt_port}")
            self.mqtt_client.connect(self.mqtt_broker, self.mqtt_port, 60)
            self.mqtt_client.loop_start()
            
            return True
        except Exception as e:
            self.logger.error(f"MQTT初始化失败: {e}")
            return False
    
    def init_serial(self):
        """初始化串口连接"""
        try:
            # 选择串口
            selected_port = self.select_serial_port()
            if not selected_port:
                return False
            
            self.serial_port = selected_port
            
            # 测试连接
            print(f"\n🔗 正在测试串口连接: {self.serial_port}")
            if not self.test_serial_connection(self.serial_port):
                print(f"⚠️  串口连接测试失败，但仍尝试建立连接...")
            
            # 建立连接
            self.serial_conn = serial.Serial(
                port=self.serial_port,
                baudrate=self.serial_baudrate,
                timeout=1,
                write_timeout=1
            )
            self.logger.info(f"串口连接成功: {self.serial_port} @ {self.serial_baudrate}")
            time.sleep(2)  # 等待STM32初始化
            return True
            
        except Exception as e:
            self.logger.error(f"串口连接失败: {e}")
            return False
    
    def on_mqtt_connect(self, client, userdata, flags, rc):
        """MQTT连接回调"""
        if rc == 0:
            self.logger.info("MQTT连接成功")
            client.subscribe(self.water_topic)
            client.subscribe(self.track_topic)
            client.subscribe(self.unlock_topic)
        else:
            self.logger.error(f"MQTT连接失败，返回码: {rc}")
    
    def on_mqtt_disconnect(self, client, userdata, rc):
        """MQTT断开连接回调"""
        self.logger.warning("MQTT连接断开")
    
    def on_mqtt_message(self, client, userdata, msg):
        """MQTT消息接收回调"""
        try:
            topic = msg.topic
            direction = msg.payload.decode('utf-8')
            
            # 根据主题确定类型
            if topic == self.water_topic:
                command = 'W' + direction
            elif topic == self.track_topic:
                command = 'T' + direction
            elif topic == self.unlock_topic:
                command = direction  # 直接使用payload作为命令
            else:
                self.logger.warning(f"未知主题: {topic}")
                return
            
            self.logger.info(f"收到命令: {command}")
            
            # 验证命令格式
            if topic == self.unlock_topic:
                # 解锁命令不需要验证格式，直接发送
                self.command_queue.put(command)
            elif self.validate_command(command):
                self.command_queue.put(command)
            else:
                self.logger.warning(f"无效命令格式: {command}")
                
        except Exception as e:
            self.logger.error(f"处理MQTT消息时出错: {e}")
    
    def validate_command(self, command):
        """验证命令格式"""
        if len(command) != 2:
            return False
        
        cmd_type = command[0].upper()
        direction = command[1].upper()
        
        # 检查类型
        if cmd_type not in ['W', 'T']:
            return False
            
        # 检查方向
        if direction not in ['F', 'B', 'L', 'R', 'S']:
            return False
            
        return True
    
    def send_to_stm32(self, command):
        """发送命令到STM32"""
        try:
            if self.serial_conn and self.serial_conn.is_open:
                self.serial_conn.write(command.encode('utf-8'))
                self.serial_conn.flush()
                self.logger.info(f"已发送到STM32: {command}")
                return True
            else:
                self.logger.error("串口未连接")
                return False
                
        except Exception as e:
            self.logger.error(f"发送到STM32时出错: {e}")
            return False
    
    def command_processor(self):
        """命令处理线程"""
        while self.running:
            try:
                # 从队列获取命令（阻塞等待）
                command = self.command_queue.get(timeout=1)
                
                # 发送到STM32
                self.send_to_stm32(command)
                
                self.command_queue.task_done()
                
            except queue.Empty:
                continue
            except Exception as e:
                self.logger.error(f"命令处理线程错误: {e}")
    
    def start(self):
        """启动桥接服务"""
        self.logger.info("正在启动BJG控制桥接服务...")
        
        # 初始化MQTT
        if not self.init_mqtt():
            return False
        
        # 初始化串口
        if not self.init_serial():
            return False
        
        # 启动处理线程
        self.running = True
        
        # 启动命令处理线程
        self.command_thread = threading.Thread(target=self.command_processor, daemon=True)
        self.command_thread.start()
        
        self.logger.info("BJG控制桥接服务启动成功!")
        
        return True
    
    def stop(self):
        """停止桥接服务"""
        self.logger.info("正在停止BJG控制桥接服务...")
        
        self.running = False
        
        # 发送停止命令到STM32
        if self.serial_conn and self.serial_conn.is_open:
            try:
                self.send_to_stm32("WS")  # 水中停止
                self.send_to_stm32("TS")  # 履带停止
            except:
                pass
        
        # 关闭MQTT连接
        if self.mqtt_client:
            self.mqtt_client.loop_stop()
            self.mqtt_client.disconnect()
        
        # 关闭串口
        if self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.close()
        
        self.logger.info("BJG控制桥接服务已停止")

def print_system_info():
    """打印系统信息"""
    print(f"操作系统: {platform.system()}")
    print(f"系统版本: {platform.release()}")
    print(f"架构: {platform.machine()}")
    if platform.system() == "Linux":
        print("注意: Ubuntu系统可能需要添加用户到dialout组:")
        print("  sudo usermod -a -G dialout $USER")
        print("  然后重新登录或重启系统")

def main():
    """主函数"""
    print("=" * 50)
    print("   BJG移动平台控制系统 - MQTT串口桥接器")
    print("=" * 50)
    
    # 打印系统信息
    print_system_info()
    print()
    
    # 配置参数
    config = {
        "mqtt_broker": "10.246.223.221",
        "mqtt_port": 7000,
        "serial_port": None,  # 自动检测
        "serial_baudrate": 115200
    }
    
    print("配置信息:")
    for key, value in config.items():
        if key == "serial_port" and value is None:
            print(f"  {key}: 自动检测")
        else:
            print(f"  {key}: {value}")
    print()
    
    # 创建桥接器实例
    bridge = MQTTSerialBridge(**config)
    
    try:
        # 启动服务
        if bridge.start():
            print("服务运行中... 按 Ctrl+C 停止")
            print("\n控制说明:")
            print("  左侧遥感 - 水中推进器控制 (WASD键)")
            print("  右侧遥感 - 履带系统控制 (方向键)")
            print("  空格键 - 紧急停止")
            print("\n请在浏览器中打开 web/index.html 开始控制")
            print()
            
            # 保持运行
            while True:
                time.sleep(1)
        else:
            print("服务启动失败!")
            
    except KeyboardInterrupt:
        print("\n收到停止信号...")
    except Exception as e:
        print(f"运行时错误: {e}")
    finally:
        bridge.stop()
        print("程序已退出")

if __name__ == "__main__":
    main()
