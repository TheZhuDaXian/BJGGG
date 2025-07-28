import cv2
import numpy as np
import serial
import time
import sys
import tkinter as tk
from tkinter import ttk, Canvas
import threading
from collections import deque
from PIL import Image, ImageTk
import math
import tkinter.messagebox

# 全局美化参数
GLOBAL_FONT = ("微软雅黑", 13)
TITLE_FONT = ("微软雅黑", 17, "bold")
SECTION_FONT = ("微软雅黑", 13, "bold")
LABEL_FONT = ("微软雅黑", 12)
INFO_FONT = ("微软雅黑", 14, "bold")
BTN_FONT = ("微软雅黑", 13, "bold")
JOYSTICK_FONT = ("微软雅黑", 11, "bold")
JOYSTICK_LABEL_FONT = ("微软雅黑", 10)
JOYSTICK_COORD_FONT = ("微软雅黑", 10)
JOYSTICK_SIZE = 260  # 遥感canvas尺寸
JOYSTICK_OUTER_RADIUS = 100
JOYSTICK_INNER_RADIUS = 28
JOYSTICK_LINE_WIDTH = 4
JOYSTICK_DOT_WIDTH = 5
JOYSTICK_LABEL_OFFSET = 20
JOYSTICK_COORD_OFFSET = 38

class JoystickControlUI:
    def __init__(self):
        try:
            self.ser = serial.Serial('com14', 115200, timeout=1)
            time.sleep(2)
        except:
            print("❌ 串口连接失败，请检查COM端口")
            sys.exit(1)
        
        self.cap = cv2.VideoCapture(1)
        if not self.cap.isOpened():
            print("❌ 无法打开摄像头")
            sys.exit(1)
        
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.cap.set(cv2.CAP_PROP_FPS, 30)
        
        self.pan_angle = 135
        self.tilt_angle = 90
        
        self.joystick_active = False
        self.joystick_x = 0  
        self.joystick_y = 0  
        
        self.tracking_mode = False
        self.running = True
        
        self.last_send_time = 0
        self.send_interval = 0.05 
        
        self.init_tracking_system()
        
        self.setup_gui()
        
        self.video_thread = threading.Thread(target=self.video_stream, daemon=True)
        self.video_thread.start()
        
        self.control_thread = threading.Thread(target=self.control_loop, daemon=True)
        self.control_thread.start()
    
    def init_tracking_system(self):
        """初始化追踪系统"""
        self.lower_red1 = np.array([0, 120, 120])
        self.upper_red1 = np.array([10, 255, 255])
        self.lower_red2 = np.array([160, 120, 120])
        self.upper_red2 = np.array([180, 255, 255])
        
        self.KP = 0.4
        self.KI = 0.0
        self.KD = 0.9
        
        self.CENTER_TOLERANCE = 18
        self.TRIGGER_THRESHOLD = 0.06
        self.TRIGGER_DELAY = 12
        self.MAX_ANGLE_CHANGE = 4.0
        self.DEAD_ZONE = 1.0
        
        self.x_filter = SimpleFilter(6)
        self.y_filter = SimpleFilter(6)
        self.pan_filter = SimpleFilter(4)
        self.tilt_filter = SimpleFilter(4)
        
        self.pan_pid = StablePID(self.KP, self.KI, self.KD)
        self.tilt_pid = StablePID(self.KP, self.KI, self.KD)
        
        self.last_pan = 135
        self.last_tilt = 90
        self.trigger_counter = 0
        self.stability_history = deque(maxlen=10)
        self.stable_frames = 0
    
    def setup_gui(self):
        """创建GUI界面"""
        self.root = tk.Tk()
        self.root.title("🎮 摄像头遥感控制系统")
        self.root.geometry("1200x800")
        self.root.minsize(900, 600)
        self.root.configure(bg='#181a1b')
        self.root.option_add("*Font", GLOBAL_FONT)
        self.root.option_add("*Label.Font", GLOBAL_FONT)
        self.root.option_add("*Button.Font", BTN_FONT)
        self.root.option_add("*TButton.Font", BTN_FONT)
        self.root.option_add("*TLabel.Font", GLOBAL_FONT)
        self.root.option_add("*TFrame.Font", GLOBAL_FONT)
        self.root.option_add("*TLabelFrame.Font", SECTION_FONT)

        self.root.resizable(True, True)

        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("TFrame", background="#23272b")
        style.configure("Main.TFrame", background="#181a1b")
        style.configure("TLabel", background="#23272b", foreground="#ffffff")
        style.configure("Title.TLabel", background="#23272b", foreground="#ffffff", font=TITLE_FONT)
        style.configure("Section.TLabelframe", background="#23272b", foreground="#ffffff", font=SECTION_FONT, borderwidth=0)
        style.configure("Section.TLabelframe.Label", background="#23272b", foreground="#ffffff", font=SECTION_FONT)
        style.configure("Info.TLabel", background="#23272b", foreground="#FFD700", font=INFO_FONT)
        style.configure("Status.TLabel", background="#23272b", foreground="#4CAF50", font=INFO_FONT)
        style.configure("ModeManual.TLabel", background="#23272b", foreground="#4CAF50", font=INFO_FONT)
        style.configure("ModeTracking.TLabel", background="#23272b", foreground="#f44336", font=INFO_FONT)
        # 统一灰色按钮风格及交互反馈增强
        style.configure(
            "Gray.TButton",
            background="#888888",
            foreground="#ffffff",
            borderwidth=2,
            focusthickness=3,
            focuscolor="#888888",
            relief="raised",
            padding=(18, 10),
            font=("微软雅黑", 14, "bold"),
            highlightthickness=0
        )
        style.map(
            "Gray.TButton",
            background=[
                ("active", "#a0a0a0"),      # 悬停加亮
                ("pressed", "#888888"),     # 按下主色
                ("disabled", "#cccccc"),    # 禁用浅灰
                ("!active", "#888888")
            ],
            foreground=[
                ("active", "#ffffff"),
                ("disabled", "#eeeeee")
            ],
            bordercolor=[
                ("active", "#2196F3"),      # 悬停边框蓝色
                ("pressed", "#6666cc"),     # 按下边框加深
                ("disabled", "#bbbbbb"),
                ("!active", "#888888")
            ],
            relief=[
                ("pressed", "sunken"),      # 按下凹陷
                ("active", "raised"),
                ("!active", "raised"),
                ("disabled", "flat")
            ],
            borderwidth=[
                ("active", 3),
                ("pressed", 3),
                ("!active", 2),
                ("disabled", 2)
            ]
        )
        # 激光状态标签样式
        style.configure("LaserStatusReady.TLabel", background="#23272b", foreground="#4CAF50", font=LABEL_FONT)
        style.configure("LaserStatusFiring.TLabel", background="#23272b", foreground="#FF5722", font=LABEL_FONT)
        style.configure("LaserStatusError.TLabel", background="#23272b", foreground="#f44336", font=LABEL_FONT)

        main_frame = ttk.Frame(self.root, style="Main.TFrame")
        main_frame.pack(fill=tk.BOTH, expand=True, padx=18, pady=18)

        left_frame = ttk.Frame(main_frame, style="TFrame")
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 18), pady=0)

        video_title = ttk.Label(left_frame, text="📹 实时图传", style="Title.TLabel", anchor="w")
        video_title.pack(pady=(10, 6), anchor="w")

        # 使用 tk.Label 以便支持 place 和更灵活的布局
        self.video_label = tk.Label(left_frame, background="#000000")
        # 关键：不使用fill=tk.X，改为fill=tk.BOTH但不expand，便于高度受控
        self.video_label.pack(side=tk.TOP, fill=tk.BOTH, expand=False, padx=14, pady=(0, 10))
        self.left_frame = left_frame  # 保存引用，便于后续获取尺寸

        # 绑定left_frame尺寸变化事件，动态调整video_label最大高度
        self.left_frame.bind("<Configure>", self.on_left_frame_resize)
        self._max_video_height = None  # 初始化最大高度

        right_frame = ttk.Frame(main_frame, style="TFrame", width=400)
        right_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=0, pady=0)
        right_frame.pack_propagate(False)

        control_title = ttk.Label(right_frame, text="🎮 控制中心", style="Title.TLabel", anchor="center")
        control_title.pack(pady=(16, 10), anchor="center")

        joystick_frame = ttk.LabelFrame(right_frame, text="🕹️ 遥感控制", style="Section.TLabelframe")
        joystick_frame.pack(fill=tk.X, padx=14, pady=8, anchor="n")

        self.joystick_canvas = Canvas(joystick_frame, width=JOYSTICK_SIZE, height=JOYSTICK_SIZE,
                                     bg='#23272b', highlightthickness=0)
        self.joystick_canvas.pack(pady=10, padx=0, anchor="center")

        self.joystick_canvas.bind("<Button-1>", self.joystick_press)
        self.joystick_canvas.bind("<B1-Motion>", self.joystick_drag)
        self.joystick_canvas.bind("<ButtonRelease-1>", self.joystick_release)

        self.draw_joystick()

        joystick_info = ttk.Label(joystick_frame,
                                 text="拖拽圆点控制方向",
                                 foreground="#cccccc", background="#23272b",
                                 font=JOYSTICK_LABEL_FONT, anchor="center")
        joystick_info.pack(pady=(0, 8), anchor="center")

        # ======= 操作按钮区（同一行，统一风格） =======
        action_frame = ttk.LabelFrame(right_frame, text="⚡ 操作区", style="Section.TLabelframe")
        action_frame.pack(fill=tk.X, padx=14, pady=8, anchor="n")

        action_btns = ttk.Frame(action_frame, style="TFrame")
        # 改为竖直三行排列，每个按钮单独一行
        action_btns.pack(fill=tk.X, pady=18, padx=0)

        # 竖直排列，每个按钮单独一行，宽度适中
        self.center_btn = ttk.Button(action_btns, text="📍归中", command=self.center_camera, style="Gray.TButton")
        self.center_btn.pack(fill=tk.X, padx=12, pady=(0, 10))

        self.laser_button = ttk.Button(action_btns, text="🔴 发射激光", command=self.fire_laser, style="Gray.TButton")
        self.laser_button.pack(fill=tk.X, padx=12, pady=(0, 10))

        self.tracking_button = ttk.Button(action_btns, text="🔴 开启追踪", command=self.toggle_tracking, style="Gray.TButton")
        self.tracking_button.pack(fill=tk.X, padx=12, pady=(0, 0))

        # 保持按钮组竖直居中，风格与之前一致

        # ======= 状态信息区（分组对齐） =======
        status_frame = ttk.LabelFrame(left_frame, text="📊 系统状态", style="Section.TLabelframe")
        status_frame.pack(fill=tk.X, padx=14, pady=(10, 0), anchor="n")

        status_container = ttk.Frame(status_frame, style="TFrame")
        status_container.pack(fill=tk.X, pady=8, padx=0)

        # 第一组：模式、目标
        info_row1 = ttk.Frame(status_container, style="TFrame")
        info_row1.pack(fill=tk.X, pady=(0, 2), padx=0)
        self.mode_label = ttk.Label(info_row1, text="模式: 手动遥感",
                                   style="ModeManual.TLabel", anchor="w")
        self.mode_label.pack(side=tk.LEFT, anchor="w", padx=(0, 16))
        self.target_label = ttk.Label(info_row1, text="目标: 未检测",
                                     style="Info.TLabel", anchor="w")
        self.target_label.pack(side=tk.LEFT, anchor="w")

        # 第二组：FPS、角度
        info_row2 = ttk.Frame(status_container, style="TFrame")
        info_row2.pack(fill=tk.X, pady=(0, 2), padx=0)
        self.fps_label = ttk.Label(info_row2, text="FPS: --",
                                  foreground="#2196F3", background="#23272b",
                                  font=LABEL_FONT, anchor="w")
        self.fps_label.pack(side=tk.LEFT, anchor="w", padx=(0, 16))
        self.angle_label = ttk.Label(info_row2, text="角度: 135°, 90°",
                                    foreground="#9C27B0", background="#23272b",
                                    font=LABEL_FONT, anchor="w")
        self.angle_label.pack(side=tk.LEFT, anchor="w")

        # 第三组：激光状态
        info_row3 = ttk.Frame(status_container, style="TFrame")
        info_row3.pack(fill=tk.X, pady=(0, 2), padx=0)
        self.laser_status_label = ttk.Label(info_row3, text="激光: 待命",
                                           style="LaserStatusReady.TLabel", anchor="w")
        self.laser_status_label.pack(side=tk.LEFT, anchor="w")

        self.laser_firing = False
        self.laser_start_time = 0


        # 绑定窗口缩放事件，动态调整布局
        # 临时移除窗口缩放事件绑定，彻底阻断递归死循环
        # self.root.bind("<Configure>", self.on_resize)
    
    def on_left_frame_resize(self, event):
        # left_frame尺寸变化时，动态设置video_label最大高度为70%
        lf_height = self.left_frame.winfo_height()
        max_video_height = int(lf_height * 0.7)
        self._max_video_height = max_video_height
        self.update_video_display()
    
    def on_resize(self, event):
        # 优化：窗口缩放时，触发画面自适应，防止递归死循环
        if hasattr(self, '_resizing') and self._resizing:
            return
        self.update_video_display()
    
    def draw_joystick(self):
        """绘制遥感"""
        self.joystick_canvas.delete("all")

        center_x, center_y = JOYSTICK_SIZE // 2, JOYSTICK_SIZE // 2
        outer_radius = JOYSTICK_OUTER_RADIUS
        inner_radius = JOYSTICK_INNER_RADIUS

        # 外圆（操作区）
        self.joystick_canvas.create_oval(center_x - outer_radius, center_y - outer_radius,
                                         center_x + outer_radius, center_y + outer_radius,
                                         outline='#bbbbbb', width=JOYSTICK_LINE_WIDTH, fill='#33363d')

        # 十字线
        self.joystick_canvas.create_line(center_x - outer_radius + 16, center_y,
                                         center_x + outer_radius - 16, center_y,
                                         fill='#666a7a', width=2)
        self.joystick_canvas.create_line(center_x, center_y - outer_radius + 16,
                                         center_x, center_y + outer_radius - 16,
                                         fill='#666a7a', width=2)

        # 方向文字
        self.joystick_canvas.create_text(center_x, center_y - outer_radius - JOYSTICK_LABEL_OFFSET,
                                         text="上", fill='#ffffff', font=JOYSTICK_FONT)
        self.joystick_canvas.create_text(center_x, center_y + outer_radius + JOYSTICK_LABEL_OFFSET,
                                         text="下", fill='#ffffff', font=JOYSTICK_FONT)
        self.joystick_canvas.create_text(center_x - outer_radius - JOYSTICK_LABEL_OFFSET, center_y,
                                         text="左", fill='#ffffff', font=JOYSTICK_FONT)
        self.joystick_canvas.create_text(center_x + outer_radius + JOYSTICK_LABEL_OFFSET, center_y,
                                         text="右", fill='#ffffff', font=JOYSTICK_FONT)

        # 圆点
        if self.joystick_active:
            inner_x = center_x - self.joystick_x * (outer_radius - inner_radius)
            inner_y = center_y + self.joystick_y * (outer_radius - inner_radius)
            color = '#FF5722'
        else:
            inner_x, inner_y = center_x, center_y
            color = '#4CAF50'

        self.joystick_canvas.create_oval(inner_x - inner_radius, inner_y - inner_radius,
                                         inner_x + inner_radius, inner_y + inner_radius,
                                         outline='#ffffff', width=JOYSTICK_DOT_WIDTH, fill=color)

        # 坐标显示
        coord_text = f"X:{self.joystick_x:.2f}, Y:{self.joystick_y:.2f}"
        self.joystick_canvas.create_text(center_x, center_y + outer_radius + JOYSTICK_COORD_OFFSET,
                                         text=coord_text, fill='#ffffff',
                                         font=JOYSTICK_COORD_FONT)
    
    def joystick_press(self, event):
        """遥感按下"""
        self.joystick_active = True
        self.update_joystick_position(event.x, event.y)
    
    def joystick_drag(self, event):
        """遥感拖拽"""
        if self.joystick_active:
            self.update_joystick_position(event.x, event.y)
    
    def joystick_release(self, event):
        """遥感释放"""
        self.joystick_active = False
        self.joystick_x = 0
        self.joystick_y = 0
        self.draw_joystick()
    
    def update_joystick_position(self, mouse_x, mouse_y):
        """更新遥感位置"""
        center_x, center_y = JOYSTICK_SIZE // 2, JOYSTICK_SIZE // 2
        max_radius = JOYSTICK_OUTER_RADIUS - JOYSTICK_INNER_RADIUS - 8
        
        dx = mouse_x - center_x
        dy = mouse_y - center_y
        
        distance = math.sqrt(dx*dx + dy*dy)
        if distance > max_radius:
            dx = dx * max_radius / distance
            dy = dy * max_radius / distance
        
        self.joystick_x = -dx / max_radius 
        self.joystick_y = dy / max_radius
        
        self.draw_joystick()
    
    def control_loop(self):
        """控制循环"""
        while self.running:
            current_time = time.time()
            
            if not self.tracking_mode and (current_time - self.last_send_time >= self.send_interval):
                if self.joystick_active and (abs(self.joystick_x) > 0.05 or abs(self.joystick_y) > 0.05):
                    pan_change = self.joystick_x * 2.0
                    tilt_change = self.joystick_y * 1.5
                    
                    self.pan_angle += pan_change
                    self.tilt_angle += tilt_change
                    
                    self.pan_angle = max(0, min(270, self.pan_angle))
                    self.tilt_angle = max(0, min(180, self.tilt_angle))
                
                # 发送控制命令
                self.send_command(self.pan_angle, self.tilt_angle, False)
                self.last_send_time = current_time
            
            time.sleep(0.02)  # 50Hz控制频率
    
    def video_stream(self):
        """视频流处理"""
        frame_count = 0
        start_time = time.time()
        self._latest_frame = None  # 缓存最新帧

        while self.running:
            ret, frame = self.cap.read()
            if not ret:
                continue

            frame_count += 1

            # 如果是追踪模式，处理追踪
            if self.tracking_mode:
                frame = self.process_tracking(frame)

            # 缓存最新帧
            self._latest_frame = frame

            # 调用自适应显示
            self.update_video_display()

            # 更新FPS
            if frame_count % 30 == 0:
                elapsed = time.time() - start_time
                fps = frame_count / elapsed
                if hasattr(self, 'fps_label'):
                    self.fps_label.configure(text=f"FPS: {fps:.1f}")
                frame_count = 0
                start_time = time.time()

            time.sleep(0.033)  # 约30FPS
    
    def process_tracking(self, frame):
        """处理追踪逻辑（与之前相同）"""
        height, width = frame.shape[:2]
        center_x, center_y = width // 2, height // 2
        
        # 绘制中心十字
        cv2.line(frame, (center_x-15, center_y), (center_x+15, center_y), (0, 255, 0), 2)
        cv2.line(frame, (center_x, center_y-15), (center_x, center_y+15), (0, 255, 0), 2)
        cv2.circle(frame, (center_x, center_y), self.CENTER_TOLERANCE, (0, 255, 0), 1)
        
        # 检测红色目标
        x, y, radius = self.detect_red_target(frame)
        
        trigger = False
        
        if x is not None:
            # 位置滤波
            self.x_filter.add(x)
            self.y_filter.add(y)
            
            filtered_x = self.x_filter.get_filtered()
            filtered_y = self.y_filter.get_filtered()
            
            if filtered_x is not None and filtered_y is not None:
                # 计算误差
                error_x = (filtered_x - center_x) / center_x
                error_y = (filtered_y - center_y) / center_y
                
                # PID控制
                pan_output = self.pan_pid.compute(error_x)
                tilt_output = self.tilt_pid.compute(error_y)
                
                # 距离自适应控制
                distance = np.sqrt((filtered_x - center_x)**2 + (filtered_y - center_y)**2)
                
                if distance > 40:
                    control_strength_pan = 70
                    control_strength_tilt = 55
                elif distance > 20:
                    control_strength_pan = 60
                    control_strength_tilt = 48
                else:
                    control_strength_pan = 50
                    control_strength_tilt = 40
                
                # 计算目标角度
                target_pan = 135 - pan_output * control_strength_pan
                target_tilt = 90 + tilt_output * control_strength_tilt
                
                # 角度滤波和平滑
                self.pan_filter.add(target_pan)
                self.tilt_filter.add(target_tilt)
                
                filtered_pan = self.pan_filter.get_filtered()
                filtered_tilt = self.tilt_filter.get_filtered()
                
                if filtered_pan is not None and filtered_tilt is not None:
                    smooth_pan = self.smooth_angle(filtered_pan, self.last_pan)
                    smooth_tilt = self.smooth_angle(filtered_tilt, self.last_tilt)
                    
                    self.pan_angle = max(0, min(270, smooth_pan))
                    self.tilt_angle = max(0, min(180, smooth_tilt))
                    
                    self.last_pan = self.pan_angle
                    self.last_tilt = self.tilt_angle
                
                # 稳定性检测
                self.stability_history.append(distance)
                if len(self.stability_history) >= 5:
                    recent_distances = list(self.stability_history)[-5:]
                    distance_variance = np.var(recent_distances)
                    if distance_variance < 2.0:
                        self.stable_frames += 1
                    else:
                        self.stable_frames = 0
                
                # 触发检测
                if (abs(error_x) < self.TRIGGER_THRESHOLD and 
                    abs(error_y) < self.TRIGGER_THRESHOLD and 
                    radius > 20 and
                    self.stable_frames > 5):
                    self.trigger_counter += 1
                    if self.trigger_counter >= self.TRIGGER_DELAY:
                        trigger = True
                else:
                    self.trigger_counter = max(0, self.trigger_counter - 1)
                
                # 绘制目标
                color = (0, 255, 0) if distance <= self.CENTER_TOLERANCE else (0, 0, 255)
                cv2.circle(frame, (int(filtered_x), int(filtered_y)), int(radius), color, 2)
                cv2.circle(frame, (int(filtered_x), int(filtered_y)), 3, color, -1)
                cv2.line(frame, (int(filtered_x), int(filtered_y)), (center_x, center_y), (255, 255, 0), 1)
                
                # 显示信息
                cv2.putText(frame, f"Distance: {distance:.1f}px", 
                           (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)
                
                if trigger:
                    cv2.putText(frame, "TARGET LOCKED!", 
                               (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
                
                # 更新状态
                self.target_label.configure(text=f"目标: 距离{distance:.1f}px")
        else:
            # 重置状态
            self.trigger_counter = 0
            self.stable_frames = 0
            self.stability_history.clear()
            self.target_label.configure(text="目标: 未检测")
        
        # 发送控制命令
        self.send_command(self.pan_angle, self.tilt_angle, trigger)
        
        return frame
    
    def detect_red_target(self, frame):
        """检测红色目标"""
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        
        mask1 = cv2.inRange(hsv, self.lower_red1, self.upper_red1)
        mask2 = cv2.inRange(hsv, self.lower_red2, self.upper_red2)
        mask = cv2.bitwise_or(mask1, mask2)
        
        kernel = np.ones((3, 3), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        if contours:
            max_contour = max(contours, key=cv2.contourArea)
            area = cv2.contourArea(max_contour)
            
            if area > 200:
                ((x, y), radius) = cv2.minEnclosingCircle(max_contour)
                if radius > 8:
                    return x, y, radius
        
        return None, None, None
    
    def smooth_angle(self, new_angle, last_angle):
        """平滑角度变化"""
        diff = new_angle - last_angle
        if abs(diff) < self.DEAD_ZONE:
            return last_angle
        if abs(diff) > self.MAX_ANGLE_CHANGE:
            return last_angle + (self.MAX_ANGLE_CHANGE if diff > 0 else -self.MAX_ANGLE_CHANGE)
        return new_angle
    
    def send_command(self, pan, tilt, trigger, laser_trigger=False):
        """发送控制命令"""
        try:
            pan_int = int(pan) & 0xFFFF
            tilt_int = int(tilt) & 0xFFFF

            # 确定触发信号值
            trigger_value = 0
            if laser_trigger:
                trigger_value = 2  # 激光触发
            elif trigger:
                trigger_value = 1  # 普通触发

            data = bytes([
                (pan_int >> 8) & 0xFF,
                pan_int & 0xFF,
                (tilt_int >> 8) & 0xFF,
                tilt_int & 0xFF,
                trigger_value
            ])

            self.ser.write(data)

            # 操作日志
            print(f"发送命令: pan={pan}, tilt={tilt}, trigger={trigger_value}")
            # 更新角度显示
            self.angle_label.configure(text=f"角度: {pan:.0f}°, {tilt:.0f}°")
        except Exception as e:
            print(f"❌ 串口命令发送失败: {e}")
            try:
                tk.messagebox.showerror("串口命令发送失败", f"串口命令发送异常：{e}")
            except Exception:
                pass
    
    def toggle_tracking(self):
        """切换追踪模式"""
        self.tracking_mode = not self.tracking_mode
        
        if self.tracking_mode:
            self.tracking_button.configure(text="🟢 关闭追踪", style="Gray.TButton")
            self.mode_label.configure(text="模式: 智能追踪", style="ModeTracking.TLabel")
        else:
            self.tracking_button.configure(text="🔴 开启追踪", style="Gray.TButton")
            self.mode_label.configure(text="模式: 手动遥感", style="ModeManual.TLabel")
            # 重置追踪状态
            self.trigger_counter = 0
            self.stable_frames = 0
            self.stability_history.clear()
    
    def fire_laser(self):
        """手动发射激光（优化异常保护与UI恢复）"""
        if self.laser_firing:
            # 已在发射中，忽略多余点击
            return
        self.laser_firing = True
        self.laser_start_time = time.time()
        try:
            # UI立即切换为发射中
            self.laser_button.configure(text="🔥 发射中...", style="Gray.TButton", state='disabled')
            self.laser_status_label.configure(text="状态: 发射中 (2秒)", style="LaserStatusFiring.TLabel")
            self.root.update_idletasks()
            # 发送激光触发命令 (trigger = 2)
            self.send_command(self.pan_angle, self.tilt_angle, True, laser_trigger=True)
            print("🔫 手动激光发射！")
        except Exception as e:
            # 异常时恢复按钮并提示
            self.laser_firing = False
            self.laser_button.configure(text="🔴 发射激光", style="Gray.TButton", state='normal')
            self.laser_status_label.configure(text="状态: 失败", style="LaserStatusError.TLabel")
            tk.messagebox.showerror("激光发射失败", f"激光发射异常：{e}")
            return
        # 2秒后自动恢复
        self.root.after(2000, self.laser_finished)
    
    def laser_finished(self):
        """激光发射结束，确保UI恢复"""
        self.laser_firing = False
        self.laser_button.configure(text="🔴 发射激光", style="Gray.TButton", state='normal')
        self.laser_status_label.configure(text="状态: 待命", style="LaserStatusReady.TLabel")
        print("✅ 激光发射完成")
    
    def center_camera(self):
        """摄像头归中"""
        if not self.tracking_mode:
            self.pan_angle = 135
            self.tilt_angle = 90
            self.send_command(135, 90, False)
    
    def close_application(self):
        """关闭应用"""
        # 若激光发射中，强制恢复按钮状态
        if getattr(self, 'laser_firing', False):
            self.laser_firing = False
            if hasattr(self, 'laser_button'):
                self.laser_button.configure(text="🔴 发射激光", style="Gray.TButton", state='normal')
            if hasattr(self, 'laser_status_label'):
                self.laser_status_label.configure(text="状态: 待命", style="LaserStatusReady.TLabel")
        self.running = False
        time.sleep(0.1)
        
        # 归中舵机
        self.send_command(135, 90, False)
        time.sleep(0.1)
        
        # 关闭资源
        if hasattr(self, 'cap'):
            self.cap.release()
        if hasattr(self, 'ser'):
            self.ser.close()
        
        self.root.quit()
        self.root.destroy()
    
    def run(self):
        """运行GUI"""
        self.root.protocol("WM_DELETE_WINDOW", self.close_application)
        self.root.mainloop()


    def update_video_display(self):
        """自适应缩放并居中显示摄像头画面，保持纵横比，防止递归死循环和无限放大，并限制最大高度"""
        if not hasattr(self, '_latest_frame') or self._latest_frame is None:
            return
        frame = self._latest_frame

        # 获取 video_label 可用宽度
        if hasattr(self, 'video_label'):
            self.video_label.update_idletasks()
            width = self.video_label.winfo_width()
            height = self.video_label.winfo_height()
            width = max(width, 100)
            height = max(height, 100)
        else:
            width, height = 640, 480

        # 原始画面尺寸
        h0, w0 = frame.shape[:2]
        aspect = w0 / h0

        # 计算最大高度（left_frame的70%），优先保证系统状态区可见
        max_video_height = getattr(self, '_max_video_height', None)
        if max_video_height is not None:
            height = min(height, max_video_height)

        # 计算目标尺寸，保持纵横比，优先放大宽度
        target_w = width
        target_h = int(target_w / aspect)
        if target_h > height:
            target_h = height
            target_w = int(target_h * aspect)

        # 限制最大尺寸，防止无限放大
        max_w, max_h = 1920, 1080
        target_w = min(target_w, max_w)
        target_h = min(target_h, max_h)

        # 转换为Tkinter可显示的格式
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        frame_pil = Image.fromarray(frame_rgb)
        frame_pil = frame_pil.resize((target_w, target_h), Image.Resampling.LANCZOS)
        frame_tk = ImageTk.PhotoImage(frame_pil)

        # 只在尺寸变化时设置，防止递归死循环
        if hasattr(self, 'video_label'):
            prev_size = getattr(self, '_prev_video_size', (None, None))
            if prev_size != (target_w, target_h):
                self._resizing = True
                self.video_label.configure(width=target_w, height=target_h)
                self._resizing = False
                self._prev_video_size = (target_w, target_h)
            self.video_label.configure(image=frame_tk)
            self.video_label.image = frame_tk

class SimpleFilter:
    """简单滤波器"""
    def __init__(self, size=6):
        self.values = deque(maxlen=size)
        
    def add(self, value):
        self.values.append(value)
        
    def get_filtered(self):
        if not self.values:
            return None
        sorted_vals = sorted(self.values)
        if len(sorted_vals) > 4:
            trimmed = sorted_vals[1:-1]
            return sum(trimmed) / len(trimmed)
        else:
            return sum(sorted_vals) / len(sorted_vals)


class StablePID:
    """稳定PID控制器"""
    def __init__(self, kp, ki, kd):
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.prev_error = 0
        self.integral = 0
        
    def compute(self, error):
        if abs(error) < 0.015:
            error = 0
            
        self.integral = 0
        derivative = error - self.prev_error
        
        error_magnitude = abs(error)
        
        if error_magnitude > 0.3:
            adaptive_kp = self.kp * 0.8
            adaptive_kd = self.kd * 1.2
        elif error_magnitude > 0.1:
            adaptive_kp = self.kp
            adaptive_kd = self.kd
        else:
            adaptive_kp = self.kp * 1.2
            adaptive_kd = self.kd * 1.5
        
        output = adaptive_kp * error + self.ki * self.integral + adaptive_kd * derivative
        
        if error_magnitude > 0.3:
            output = max(-0.25, min(0.25, output))
        else:
            output = max(-0.4, min(0.4, output))
        
        self.prev_error = error
        return output


if __name__ == "__main__":
    print("🎮 启动摄像头遥感控制系统...")
    app = JoystickControlUI()
    app.run()

