#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
游隼战戟--致远舰远洋登陆综合打击平台 控制中心
用户端控制界面 - 通过MQTT发送命令到工控机

版本: v2.0
作者: 游隼战戟开发团队
"""

import sys
import time
import threading
from datetime import datetime

# 尝试导入图形界面库
try:
    import tkinter as tk
    from tkinter import ttk, scrolledtext, messagebox
    GUI_AVAILABLE = True
except ImportError:
    GUI_AVAILABLE = False

# 尝试导入串口库
try:
    import serial
    import serial.tools.list_ports
    SERIAL_AVAILABLE = True
except ImportError:
    SERIAL_AVAILABLE = False
class SerialController:
    """串口控制器"""
    def __init__(self, port=None, baudrate=115200):
        self.port = port
        self.baudrate = baudrate
        self.serial = None
        self.running = False
        self.data_callback = None
        self.status_callback = None
        self.debug_callback = None
        self._recv_thread = None

    def set_callbacks(self, data_callback=None, status_callback=None, debug_callback=None):
        self.data_callback = data_callback
        self.status_callback = status_callback
        self.debug_callback = debug_callback

    def connect(self):
        if not SERIAL_AVAILABLE or not self.port:
            if self.status_callback:
                self.status_callback(False)
            return False
        try:
            self.serial = serial.Serial(self.port, self.baudrate, timeout=0.5)
            self.running = True
            if self.status_callback:
                self.status_callback(True)
            self._recv_thread = threading.Thread(target=self._recv_loop, daemon=True)
            self._recv_thread.start()
            if self.debug_callback:
                self.debug_callback(f"串口已连接: {self.port} @ {self.baudrate}")
            return True
        except Exception as e:
            if self.status_callback:
                self.status_callback(False)
            if self.debug_callback:
                self.debug_callback(f"串口连接失败: {e}")
            return False

    def disconnect(self):
        self.running = False
        if self.serial:
            try:
                self.serial.close()
            except Exception:
                pass
            self.serial = None
        if self.status_callback:
            self.status_callback(False)
        if self.debug_callback:
            self.debug_callback("串口已断开")

    def send_command(self, command):
        if self.serial and self.running:
            try:
                msg = command.strip() + '\n'
                self.serial.write(msg.encode('utf-8'))
                if self.debug_callback:
                    self.debug_callback(f"串口发送: {msg.strip()}")
                return True
            except Exception as e:
                if self.debug_callback:
                    self.debug_callback(f"串口发送失败: {e}")
                return False
        return False

    def _recv_loop(self):
        while self.running and self.serial:
            try:
                line = self.serial.readline()
                if line:
                    data = line.decode('utf-8', errors='ignore').strip()
                    if self.data_callback:
                        self.data_callback(data)
            except Exception:
                pass

# 这里将实现 SerialController 类，后续插入

class BJGControlGUI:
    """图形界面控制器"""
    
    def __init__(self):
        if not GUI_AVAILABLE:
            raise ImportError("Tkinter不可用")
            
        self.root = tk.Tk()
        self.controller = None
        self.setup_ui()

    def get_serial_ports(self):
        """获取可用串口列表"""
        try:
            ports = serial.tools.list_ports.comports()
            return [port.device for port in ports]
        except Exception:
            return []

    def refresh_serial_ports(self):
        """刷新串口下拉框"""
        ports = self.get_serial_ports()
        self.port_combo['values'] = ports
        if ports and self.port_var.get() not in ports:
            self.port_var.set(ports[0])
    def setup_ui(self):
        """设置用户界面"""
        self.root.title("游隼战戟控制中心 - 串口模式 (鼠标长按控制)")
        self.root.geometry("1000x800")
        self.root.configure(bg='#2c3e50')

        # 设置样式
        style = ttk.Style()
        style.theme_use('clam')

        # 自定义样式
        style.configure('Title.TLabel',
                       font=('Microsoft YaHei', 18, 'bold'),
                       foreground='white',
                       background='#2c3e50')
        style.configure('Subtitle.TLabel',
                       font=('Microsoft YaHei', 10),
                       foreground='#ecf0f1',
                       background='#2c3e50')
        style.configure('Custom.TLabelFrame',
                       background='#34495e',
                       foreground='white',
                       borderwidth=2,
                       relief='raised')
        style.configure('Custom.TLabelFrame.Label',
                       font=('Microsoft YaHei', 11, 'bold'),
                       foreground='#3498db',
                       background='#34495e')
        style.configure('Emergency.TButton',
                       background='#e74c3c',
                       foreground='white',
                       font=('Microsoft YaHei', 10, 'bold'))
        style.configure('Connect.TButton',
                       background='#27ae60',
                       foreground='white',
                       font=('Microsoft YaHei', 9, 'bold'))
        style.configure('Control.TButton',
                       background='#3498db',
                       foreground='white',
                       font=('Microsoft YaHei', 8))

        # 主标题
        title_frame = tk.Frame(self.root, bg='#2c3e50')
        title_frame.pack(fill=tk.X, padx=15, pady=10)

        title_label = tk.Label(title_frame,
                              text="🚢 游隼战戟--致远舰远洋登陆综合打击平台",
                              font=('Microsoft YaHei', 18, 'bold'),
                              foreground='#ecf0f1',
                              background='#2c3e50')
        title_label.pack()

        subtitle_label = tk.Label(title_frame,
                                 text="控制中心 v2.0 - 串口模式 (鼠标长按控制)",
                                 font=('Microsoft YaHei', 12),
                                 foreground='#bdc3c7',
                                 background='#2c3e50')
        subtitle_label.pack(pady=(5, 0))

        # 连接设置框架
        conn_frame = tk.LabelFrame(self.root,
                                  text=" 🛠️ 串口连接设置 ",
                                  font=('Microsoft YaHei', 11, 'bold'),
                                  foreground='#3498db',
                                  background='#34495e',
                                  bd=2,
                                  relief='raised')
        conn_frame.pack(fill=tk.X, padx=15, pady=10)

        # 内容容器
        conn_content = tk.Frame(conn_frame, bg='#34495e')
        conn_content.pack(fill=tk.X, padx=10, pady=10)

        # 串口选择
        port_frame = tk.Frame(conn_content, bg='#34495e')
        port_frame.pack(fill=tk.X, pady=5)

        tk.Label(port_frame, text="串口:",
                font=('Microsoft YaHei', 10),
                foreground='white', background='#34495e').pack(side=tk.LEFT)

        self.port_var = tk.StringVar()
        self.port_combo = ttk.Combobox(port_frame, textvariable=self.port_var, width=20, font=('Consolas', 10))
        self.port_combo['values'] = self.get_serial_ports()
        self.port_combo.pack(side=tk.LEFT, padx=(10, 15))
        self.port_combo.bind("<Button-1>", lambda e: self.refresh_serial_ports())

        # 波特率
        tk.Label(port_frame, text="波特率:",
                font=('Microsoft YaHei', 10),
                foreground='white', background='#34495e').pack(side=tk.LEFT)

        self.baud_var = tk.StringVar(value="115200")
        self.baud_entry = tk.Entry(port_frame,
                                 textvariable=self.baud_var,
                                 width=8,
                                 font=('Consolas', 10),
                                 bg='#ecf0f1',
                                 fg='#2c3e50',
                                 insertbackground='#2c3e50')
        self.baud_entry.pack(side=tk.LEFT, padx=(10, 15))

        # 连接按钮
        self.connect_btn = tk.Button(port_frame,
                                   text="🔗 连接",
                                   command=self.toggle_connection,
                                   font=('Microsoft YaHei', 10, 'bold'),
                                   bg='#27ae60',
                                   fg='white',
                                   activebackground='#2ecc71',
                                   activeforeground='white',
                                   relief='raised',
                                   bd=2,
                                   padx=15)
        self.connect_btn.pack(side=tk.RIGHT)

        # 连接状态指示
        status_frame = tk.Frame(conn_content, bg='#34495e')
        status_frame.pack(fill=tk.X, pady=(5, 0))

        self.status_label = tk.Label(status_frame,
                                   text="● 未连接",
                                   font=('Microsoft YaHei', 10, 'bold'),
                                   foreground='#e74c3c',
                                   background='#34495e')
        self.status_label.pack(anchor=tk.W)
        
        # 控制区域框架
        control_frame = tk.LabelFrame(self.root, 
                                    text=" 🎮 设备控制 (鼠标长按控制) ",
                                    font=('Microsoft YaHei', 11, 'bold'),
                                    foreground='#3498db',
                                    background='#34495e',
                                    bd=2,
                                    relief='raised')
        control_frame.pack(fill=tk.X, padx=15, pady=10)
        
        # 控制区域内容
        control_content = tk.Frame(control_frame, bg='#34495e')
        control_content.pack(fill=tk.X, padx=10, pady=10)
        
        # 推进器控制区域 (左侧)
        thruster_frame = tk.Frame(control_content, bg='#34495e')
        thruster_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))
        
        thruster_title = tk.Label(thruster_frame, 
                                text="🌊 推进器控制",
                                font=('Microsoft YaHei', 12, 'bold'),
                                foreground='#3498db',
                                background='#34495e')
        thruster_title.pack(pady=(0, 15))
        
        # 推进器按键布局 - 十字形
        thruster_grid = tk.Frame(thruster_frame, bg='#34495e')
        thruster_grid.pack(pady=10)
        
        # 定义长按按钮样式
        btn_style = {
            'font': ('Microsoft YaHei', 11, 'bold'),
            'width': 8,
            'height': 2,
            'relief': 'raised',
            'bd': 3,
            'activebackground': '#2980b9',
            'activeforeground': 'white'
        }
        
        # 推进器前进按钮
        self.thruster_forward_btn = tk.Button(thruster_grid, 
                                            text="⬆\n前进",
                                            bg='#3498db',
                                            fg='white',
                                            **btn_style)
        self.thruster_forward_btn.grid(row=0, column=1, padx=5, pady=5)
        self.setup_long_press(self.thruster_forward_btn, "WF", "推进器前进", "WS", "推进器停止")
        
        # 推进器左转按钮
        self.thruster_left_btn = tk.Button(thruster_grid, 
                                         text="⬅\n左转",
                                         bg='#3498db',
                                         fg='white',
                                         **btn_style)
        self.thruster_left_btn.grid(row=1, column=0, padx=5, pady=5)
        self.setup_long_press(self.thruster_left_btn, "WL", "推进器左转", "WS", "推进器停止")
        
        # 推进器停止按钮
        self.thruster_stop_btn = tk.Button(thruster_grid, 
                                         text="⏹\n停止",
                                         bg='#e74c3c',
                                         fg='white',
                                         **btn_style)
        self.thruster_stop_btn.grid(row=1, column=1, padx=5, pady=5)
        self.thruster_stop_btn.configure(command=lambda: self.send_command("WS", "推进器停止"))
        
        # 推进器右转按钮
        self.thruster_right_btn = tk.Button(thruster_grid, 
                                          text="➡\n右转",
                                          bg='#3498db',
                                          fg='white',
                                          **btn_style)
        self.thruster_right_btn.grid(row=1, column=2, padx=5, pady=5)
        self.setup_long_press(self.thruster_right_btn, "WR", "推进器右转", "WS", "推进器停止")
        
        # 履带控制区域 (右侧)
        track_frame = tk.Frame(control_content, bg='#34495e')
        track_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10, 0))
        
        track_title = tk.Label(track_frame, 
                             text="🚂 履带控制",
                             font=('Microsoft YaHei', 12, 'bold'),
                             foreground='#e67e22',
                             background='#34495e')
        track_title.pack(pady=(0, 15))
        
        # 履带按键布局 - 垂直排列
        track_grid = tk.Frame(track_frame, bg='#34495e')
        track_grid.pack(pady=10)
        
        btn_style_orange = btn_style.copy()
        btn_style_orange.update({'activebackground': '#d35400'})
        
        # 履带前进按钮
        self.track_forward_btn = tk.Button(track_grid, 
                                         text="⬆\n前进",
                                         bg='#e67e22',
                                         fg='white',
                                         **btn_style_orange)
        self.track_forward_btn.pack(pady=5)
        self.setup_long_press(self.track_forward_btn, "TF", "履带前进", "TS", "履带停止")
        
        # 履带停止按钮
        self.track_stop_btn = tk.Button(track_grid, 
                                      text="⏹\n停止",
                                      bg='#e74c3c',
                                      fg='white',
                                      **btn_style_orange)
        self.track_stop_btn.pack(pady=5)
        self.track_stop_btn.configure(command=lambda: self.send_command("TS", "履带停止"))
        
        # 履带后退按钮
        self.track_backward_btn = tk.Button(track_grid, 
                                          text="⬇\n后退",
                                          bg='#e67e22',
                                          fg='white',
                                          **btn_style_orange)
        self.track_backward_btn.pack(pady=5)
        self.setup_long_press(self.track_backward_btn, "TB", "履带后退", "TS", "履带停止")
        
        # 特殊功能控制
        special_frame = tk.LabelFrame(self.root, 
                                    text=" ⚙️ 特殊功能 ",
                                    font=('Microsoft YaHei', 11, 'bold'),
                                    foreground='#9b59b6',
                                    background='#34495e',
                                    bd=2,
                                    relief='raised')
        special_frame.pack(fill=tk.X, padx=15, pady=10)
        
        special_content = tk.Frame(special_frame, bg='#34495e')
        special_content.pack(fill=tk.X, padx=10, pady=10)
        
        special_btn_frame = tk.Frame(special_content, bg='#34495e')
        special_btn_frame.pack()
        
        # 解锁电调按钮
        unlock_btn = tk.Button(special_btn_frame, 
                              text="🔓 解锁电调",
                              command=lambda: self.send_command("UNLOCK", "解锁电调"),
                              font=('Microsoft YaHei', 10, 'bold'),
                              bg='#9b59b6',
                              fg='white',
                              activebackground='#8e44ad',
                              activeforeground='white',
                              relief='raised',
                              bd=2,
                              padx=15)
        unlock_btn.pack(side=tk.LEFT, padx=5)
        
        # 软件复位按钮
        reset_btn = tk.Button(special_btn_frame, 
                             text="🔄 软件复位",
                             command=self.software_reset,
                             font=('Microsoft YaHei', 10, 'bold'),
                             bg='#f39c12',
                             fg='white',
                             activebackground='#e67e22',
                             activeforeground='white',
                             relief='raised',
                             bd=2,
                             padx=15)
        reset_btn.pack(side=tk.LEFT, padx=5)
        
        # 紧急停止按钮
        emergency_btn = tk.Button(special_btn_frame, 
                                 text="🛑 紧急停止",
                                 command=self.emergency_stop,
                                 font=('Microsoft YaHei', 12, 'bold'),
                                 bg='#e74c3c',
                                 fg='white',
                                 activebackground='#c0392b',
                                 activeforeground='white',
                                 relief='raised',
                                 bd=3,
                                 padx=20,
                                 pady=5)
        emergency_btn.pack(side=tk.LEFT, padx=15)
        
        # 状态和日志区域
        info_frame = tk.LabelFrame(self.root, 
                                 text=" 📊 状态监控与日志 ",
                                 font=('Microsoft YaHei', 11, 'bold'),
                                 foreground='#27ae60',
                                 background='#34495e',
                                 bd=2,
                                 relief='raised')
        info_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=10)
        
        info_content = tk.Frame(info_frame, bg='#34495e')
        info_content.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # 状态显示区域
        status_display_frame = tk.Frame(info_content, bg='#34495e')
        status_display_frame.pack(fill=tk.X, pady=(0, 10))
        
        # 设备状态指示
        device_status_frame = tk.Frame(status_display_frame, bg='#34495e')
        device_status_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        tk.Label(device_status_frame, 
                text="设备状态:", 
                font=('Microsoft YaHei', 10, 'bold'),
                foreground='white',
                background='#34495e').pack(side=tk.LEFT)
        
        self.thruster_status = tk.Label(device_status_frame, 
                                      text="推进器: 停止", 
                                      font=('Microsoft YaHei', 9),
                                      foreground='#95a5a6',
                                      background='#34495e')
        self.thruster_status.pack(side=tk.LEFT, padx=(20, 0))
        
        self.track_status = tk.Label(device_status_frame, 
                                   text="履带: 停止", 
                                   font=('Microsoft YaHei', 9),
                                   foreground='#95a5a6',
                                   background='#34495e')
        self.track_status.pack(side=tk.LEFT, padx=(20, 0))
        
        # 日志显示区域
        log_scroll_frame = tk.Frame(info_content, bg='#34495e')
        log_scroll_frame.pack(fill=tk.BOTH, expand=True)
        
        self.log_text = scrolledtext.ScrolledText(log_scroll_frame,
                                                height=12,
                                                font=('Consolas', 9),
                                                bg='#2c3e50',
                                                fg='#ecf0f1',
                                                insertbackground='white',
                                                selectbackground='#3498db',
                                                wrap=tk.WORD,
                                                state=tk.DISABLED)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        # 底部状态栏
        self.status_bar = tk.Label(self.root,
                                  text="程序启动完成 - 请连接串口",
                                  font=('Microsoft YaHei', 9),
                                  foreground='white',
                                  background='#2c3e50',
                                  relief='sunken',
                                  anchor='w')
        self.status_bar.pack(fill=tk.X, side=tk.BOTTOM)

        # 设置键盘快捷键支持（可选）
        self.root.bind('<KeyPress>', self.on_key_press)
        self.root.focus_set()

        # 启动时显示日志
        self.log("游隼战戟控制中心启动完成")
        self.log("使用鼠标长按控制按钮进行设备控制")
        self.log("请先连接串口")
        
    def send_command(self, command, description):
        """发送命令并记录日志"""
        if self.controller and self.controller.send_command(command):
            self.log(f"发送命令: {command} ({description})")
            return True
        else:
            self.log(f"发送失败: {command} ({description}) - 串口未连接")
            return False

    def toggle_connection(self):
        """切换串口连接状态"""
        if self.controller and self.controller.running:
            # 断开连接
            self.controller.disconnect()
            self.connect_btn.config(text="🔗 连接", bg='#27ae60')
        else:
            # 尝试连接
            port = self.port_var.get().strip()
            try:
                baudrate = int(self.baud_var.get().strip())
            except ValueError:
                messagebox.showerror("错误", "波特率必须为数字")
                return

            self.connect_btn.config(text="⏳ 连接中...", bg='#f39c12')
            self.root.update()

            self.controller = SerialController(port=port, baudrate=baudrate)
            self.controller.set_callbacks(self.on_serial_data, self.on_serial_status, self.on_serial_debug)

            if self.controller.connect():
                self.connect_btn.config(text="🔌 断开", bg='#e74c3c')
            else:
                self.connect_btn.config(text="🔗 连接", bg='#27ae60')
                messagebox.showerror("连接失败", "无法连接到串口")

    def emergency_stop(self):
        """紧急停止"""
        self.log("🛑 执行紧急停止!")
        self.send_command("TS", "履带停止")
        self.send_command("WS", "推进器停止")
        # 更新状态显示
        self.thruster_status.config(text="推进器: 停止", foreground='#95a5a6')
        self.track_status.config(text="履带: 停止", foreground='#95a5a6')
        
    def software_reset(self):
        """执行软件复位"""
        # 显示确认对话框
        result = messagebox.askyesno("确认复位", 
                                   "确定要执行软件复位吗？\n\n这将重启STM32控制器，所有设备将停止工作。", 
                                   icon='warning')
        if result:
            self.log("🔄 执行软件复位...")
            if self.controller.send_command("RESET"):
                self.log("软件复位命令已发送")
                self.status_bar.config(text="软件复位命令已发送 - STM32将重启")
                # 重置设备状态显示
                self.thruster_status.config(text="推进器: 复位中", foreground='#f39c12')
                self.track_status.config(text="履带: 复位中", foreground='#f39c12')
                # 3秒后恢复状态显示
                self.root.after(3000, self.reset_device_status)
            else:
                self.log("软件复位失败: MQTT未连接")
                messagebox.showerror("错误", "软件复位失败：MQTT未连接")
    
    def reset_device_status(self):
        """复位后重置设备状态显示"""
        self.thruster_status.config(text="推进器: 停止", foreground='#95a5a6')
        self.track_status.config(text="履带: 停止", foreground='#95a5a6')
        self.log("设备状态已重置")

    def on_key_press(self, event):
        """处理按键事件（可选的键盘快捷键支持）"""
        key = event.char.lower()
        
        # 只有在焦点不在输入框时才处理快捷键
        if self.root.focus_get() in [self.server_entry, self.port_entry]:
            return
            
        if key == 'w':
            self.send_command("TF", "履带前进")
        elif key == 's':
            self.send_command("TB", "履带后退")
        elif key == 'j':
            self.send_command("TS", "履带停止")
        elif key == 'a':
            self.send_command("WL", "推进器左转")
        elif key == 'd':
            self.send_command("WR", "推进器右转")
        elif key == 'i':
            self.send_command("WF", "推进器前进")
        elif key == 'k':
            self.send_command("WS", "推进器停止")
        elif key == 'u':
            self.send_command("UNLOCK", "解锁电调")
        elif key == 'r':
            self.software_reset()
        elif key == ' ':
            self.emergency_stop()
            
    def on_serial_data(self, data):
        """处理串口数据"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log(f"STM32回复: {data}")

    def on_serial_debug(self, debug_info):
        """处理串口调试信息"""
        self.log(f"调试: {debug_info}")

    def on_serial_status(self, connected):
        """处理串口连接状态"""
        if connected:
            self.status_label.config(text="● 已连接", foreground="green")
            self.log("串口连接成功")
            self.status_bar.config(text="串口已连接 - 可以发送命令")
        else:
            self.status_label.config(text="● 未连接", foreground="red")
            self.log("串口连接断开")
            self.status_bar.config(text="串口连接断开")
            
    def log(self, message):
        """添加日志"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_message = f"[{timestamp}] {message}\n"
        
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, log_message)
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)
        
    def run(self):
        """运行GUI程序"""
        try:
            self.root.mainloop()
        except KeyboardInterrupt:
            pass
        finally:
            self.controller.disconnect()

    def setup_long_press(self, button, press_command, press_desc, release_command, release_desc):
        """设置按钮的长按功能"""
        button.press_command = press_command
        button.press_desc = press_desc
        button.release_command = release_command
        button.release_desc = release_desc
        button.is_pressed = False
        button.press_timer = None
        
        # 绑定鼠标事件
        button.bind("<ButtonPress-1>", lambda e: self.on_button_press(button))
        button.bind("<ButtonRelease-1>", lambda e: self.on_button_release(button))
        button.bind("<Leave>", lambda e: self.on_button_release(button))  # 鼠标离开也触发释放
        
    def on_button_press(self, button):
        """按钮按下事件"""
        if not button.is_pressed:
            button.is_pressed = True
            # 立即发送按下命令
            self.send_command(button.press_command, button.press_desc)
            # 设置按钮视觉反馈
            self.set_button_pressed_style(button)
            # 更新设备状态显示
            self.update_device_status(button.press_command, button.press_desc)
            
    def on_button_release(self, button):
        """按钮释放事件"""
        if button.is_pressed:
            button.is_pressed = False
            # 发送释放命令
            self.send_command(button.release_command, button.release_desc)
            # 恢复按钮视觉效果
            self.set_button_normal_style(button)
            # 更新设备状态显示
            self.update_device_status(button.release_command, button.release_desc)
            
    def set_button_pressed_style(self, button):
        """设置按钮按下时的样式"""
        current_bg = button.cget('bg')
        if current_bg == '#3498db':  # 推进器按钮
            button.config(bg='#2980b9', relief='sunken')
        elif current_bg == '#e67e22':  # 履带按钮
            button.config(bg='#d35400', relief='sunken')
            
    def set_button_normal_style(self, button):
        """设置按钮正常状态的样式"""
        # 根据按钮类型恢复原色
        button_text = button.cget('text')
        if '推进器' in button.press_desc:
            button.config(bg='#3498db', relief='raised')
        elif '履带' in button.press_desc:
            button.config(bg='#e67e22', relief='raised')
            
    def update_device_status(self, command, description):
        """更新设备状态显示"""
        if command.startswith('W'):  # 推进器命令
            if command == 'WS':
                self.thruster_status.config(text="推进器: 停止", foreground='#95a5a6')
            elif command == 'WF':
                self.thruster_status.config(text="推进器: 前进", foreground='#3498db')
            elif command == 'WL':
                self.thruster_status.config(text="推进器: 左转", foreground='#3498db')
            elif command == 'WR':
                self.thruster_status.config(text="推进器: 右转", foreground='#3498db')
        elif command.startswith('T'):  # 履带命令
            if command == 'TS':
                self.track_status.config(text="履带: 停止", foreground='#95a5a6')
            elif command == 'TF':
                self.track_status.config(text="履带: 前进", foreground='#e67e22')
            elif command == 'TB':
                self.track_status.config(text="履带: 后退", foreground='#e67e22')

class BJGControlConsole:
    """控制台界面控制器"""
    
    def __init__(self):
        self.controller = None

    def on_serial_data(self, data):
        """处理串口数据"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] STM32回复: {data}")

    def connect(self):
        """连接串口"""
        print("串口连接设置")
        import serial.tools.list_ports

        while True:
            ports = [port.device for port in serial.tools.list_ports.comports()]
            print("可用串口：", ports)
            port = input("请输入串口号 (如 COM3 或 /dev/ttyUSB0): ").strip()
            if not port:
                if ports:
                    port = ports[0]
                else:
                    print("未检测到可用串口")
                    continue

            baud_str = input("请输入波特率 (默认115200): ").strip()
            if not baud_str:
                baudrate = 115200
            else:
                try:
                    baudrate = int(baud_str)
                except ValueError:
                    print("波特率必须为数字")
                    continue

            self.controller = SerialController(port=port, baudrate=baudrate)
            self.controller.set_callbacks(self.on_serial_data)
            print(f"正在连接串口 {port} @ {baudrate} ...")
            if self.controller.connect():
                print(f"✓ 串口 {port} @ {baudrate} 连接成功")
                return True
            else:
                print(f"✗ 串口 {port} 连接失败")
                retry = input("是否重试? (y/n): ").strip().lower()
                if retry != 'y':
                    return False
                    
    def send_command(self, command, description):
        """发送命令"""
        if self.controller and self.controller.send_command(command):
            timestamp = datetime.now().strftime("%H:%M:%S")
            print(f"[{timestamp}] 发送: {command} ({description})")
        else:
            print("发送失败: 串口未连接")
            
    def print_help(self):
        """打印帮助"""
        print("""
========================================
    游隼战戟控制中心 - 键盘模式
========================================

控制按键:
  W  - 履带前进     S  - 履带后退
  A  - 推进器左转   D  - 推进器右转
  I  - 推进器前进   K  - 推进器停止
  J  - 履带停止     空格 - 紧急停止
  U  - 解锁电调     R  - 软件复位
  H  - 显示帮助     Q  - 退出程序

注意事项:
⚠️  履带和推进器请勿同时使用
⚠️  紧急情况请立即按空格键停止
⚠️  首次使用请按 U 解锁电调
⚠️  设备异常时可以按 R 执行软件复位
        """)
        
    def run(self):
        """运行控制台程序"""
        print("游隼战戟--致远舰远洋登陆综合打击平台")
        print("控制中心 v2.0 - 控制台模式")
        print("=" * 50)
        
        if not self.connect():
            print("连接失败，程序退出")
            return
            
        self.print_help()
        
        try:
            while True:
                try:
                    # 尝试获取单个按键
                    try:
                        import msvcrt
                        key = msvcrt.getch().decode('utf-8').lower()
                    except ImportError:
                        # Linux/Mac
                        key = input("请输入命令 (h显示帮助): ").strip().lower()
                        if len(key) == 0:
                            continue
                        key = key[0]
                except KeyboardInterrupt:
                    break
                
                # 处理按键
                if key == 'q':
                    print("\n退出程序...")
                    break
                elif key == 'h':
                    self.print_help()
                elif key == 'w':
                    self.send_command("TF", "履带前进")
                elif key == 's':
                    self.send_command("TB", "履带后退")
                elif key == 'j':
                    self.send_command("TS", "履带停止")
                elif key == 'a':
                    self.send_command("WL", "推进器左转")
                elif key == 'd':
                    self.send_command("WR", "推进器右转")
                elif key == 'i':
                    self.send_command("WF", "推进器前进")
                elif key == 'k':
                    self.send_command("WS", "推进器停止")
                elif key == ' ':
                    print("\n🛑 执行紧急停止!")
                    self.send_command("TS", "履带停止")
                    self.send_command("WS", "推进器停止")
                elif key == 'u':
                    self.send_command("UNLOCK", "解锁电调")
                elif key == 'r':
                    print("\n🔄 执行软件复位...")
                    self.send_command("RESET", "软件复位")
                    print("软件复位命令已发送，STM32将重启")
                else:
                    print(f"未知按键: {key} (按 h 查看帮助)")
                    
        except KeyboardInterrupt:
            print("\n检测到Ctrl+C，退出程序...")
        finally:
            self.controller.disconnect()
            print("已断开MQTT连接，程序结束")

def main():
    """主函数"""
    print("游隼战戟--致远舰远洋登陆综合打击平台")
    print("控制中心 v2.0")
    print("=" * 50)
    
    # 选择界面模式
    if GUI_AVAILABLE:
        print("检测到图形界面支持")
        choice = input("选择模式:\n1. 图形界面 (推荐)\n2. 控制台模式\n请选择 (1/2): ").strip()
        
        if choice == "1" or choice == "":
            try:
                app = BJGControlGUI()
                app.run()
                return
            except Exception as e:
                print(f"图形界面启动失败: {str(e)}")
                print("切换到控制台模式...")
    
    # 控制台模式
    try:
        app = BJGControlConsole()
        app.run()
    except Exception as e:
        print(f"程序异常: {str(e)}")
        input("按回车键退出...")

if __name__ == "__main__":
    main()
