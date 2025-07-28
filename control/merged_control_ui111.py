import sys
import time
import threading
import math
import cv2
import numpy as np
import serial
import serial.tools.list_ports
from collections import deque
from datetime import datetime
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from PIL import Image, ImageTk

# DPI感知与字体多平台兼容
def get_dpi_scaling(root):
    try:
        scaling = root.tk.call('tk', 'scaling')
        if scaling < 1.0:
            scaling = 1.0
        return scaling
    except Exception:
        return 1.0

FONT_FAMILIES = ("Microsoft YaHei", "PingFang SC", "Arial", "Segoe UI Emoji", "sans-serif")
def font(size, weight="normal"):
    return (FONT_FAMILIES, int(size), weight)

# 主题色
PRIMARY_COLOR = "#3498db"
SECONDARY_COLOR = "#34495e"
ACCENT_COLOR = "#FFD700"
BG_COLOR = "#f7f9fa"
FG_COLOR = "#23272b"
GRAY_COLOR = "#bbbbbb"
ERROR_COLOR = "#e74c3c"
SUCCESS_COLOR = "#27ae60"
DISABLED_COLOR = "#bdc3c7"

# 控件尺寸（DPI自适应）
BASE_SIZE = 13
def scale_size(root, base):
    return int(base * get_dpi_scaling(root))

# emoji字体备选
EMOJI_FONT = ("Segoe UI Emoji", "Apple Color Emoji", "Noto Color Emoji", "Arial Unicode MS", "sans-serif")

# Joystick参数
JOYSTICK_SIZE = 220
JOYSTICK_OUTER_RADIUS = 85
JOYSTICK_INNER_RADIUS = 22
JOYSTICK_LINE_WIDTH = 4
JOYSTICK_DOT_WIDTH = 5
JOYSTICK_LABEL_OFFSET = 18
JOYSTICK_COORD_OFFSET = 30

class SimpleFilter:
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

class MergedControlUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("综合控制中心")
        self.base_width = 1500
        self.base_height = 900
        self.scale_factor = 1.0
        self.root.geometry(f"{self.base_width}x{self.base_height}")
        self.root.configure(bg=BG_COLOR)
        self.root.option_add("*Font", font(BASE_SIZE))
        self.root.option_add("*TCombobox*Listbox.font", font(BASE_SIZE))
        self.root.option_add("*TButton*Font", font(BASE_SIZE, "bold"))
        self.root.option_add("*TLabel*Font", font(BASE_SIZE))
        self.root.option_add("*TEntry*Font", font(BASE_SIZE))
        self.root.option_add("*TLabel*background", BG_COLOR)
        self.root.option_add("*TFrame*background", BG_COLOR)
        self.root.option_add("*TLabel*foreground", FG_COLOR)
        self.root.option_add("*TButton*foreground", FG_COLOR)
        self.root.option_add("*TButton*background", PRIMARY_COLOR)
        self.root.tk.call("tk", "scaling", get_dpi_scaling(self.root))
        self.root.bind("<Configure>", self.on_window_resize)

        # 独立串口
        self.motion_ser = None
        self.gimbal_ser = None
        self.motion_confirmed_port = None
        self.motion_confirmed_baud = None
        self.gimbal_confirmed_port = None
        self.gimbal_confirmed_baud = None

        self.cap = None
        self.pan_angle = 135
        self.tilt_angle = 90
        self.tracking_mode = False
        self.laser_firing = False
        self.running = True
        self.joystick_active = False
        self.joystick_x = 0
        self.joystick_y = 0
        self.log_lines = deque(maxlen=200)
# 主Frame外包裹一层白色背景Frame用于居中和填充
        self.bg_frame = tk.Frame(self.root, bg="#fff")
        self.bg_frame.place(relx=0, rely=0, relwidth=1, relheight=1)

        # 追踪相关
        self.init_tracking_system()

        # 主布局 grid 三列
        # 主内容Frame放到白色背景Frame中
        self.main_frame = ttk.Frame(self.bg_frame, style="Main.TFrame")
        self.main_frame.place(x=0, y=0, width=self.base_width, height=self.base_height)
        # 后续所有main_frame替换为self.main_frame
        main_frame = self.main_frame
        main_frame.grid_rowconfigure(0, weight=1)
        main_frame.grid_columnconfigure(0, weight=1, minsize=scale_size(self.root, 220))
        main_frame.grid_columnconfigure(1, weight=1, minsize=scale_size(self.root, 400))
        main_frame.grid_columnconfigure(2, weight=1, minsize=scale_size(self.root, 220))

        # 左侧：运动/串口/特殊功能（Canvas+Scrollbar，宽度固定可收缩）
        left_canvas = tk.Canvas(main_frame, bg=BG_COLOR, highlightthickness=0)
        left_scrollbar = ttk.Scrollbar(main_frame, orient="vertical", command=left_canvas.yview)
        left_canvas.grid(row=0, column=0, sticky="nsew")
        left_scrollbar.grid(row=0, column=0, sticky="nse")
        left_canvas.configure(yscrollcommand=left_scrollbar.set)
        left_inner = tk.Frame(left_canvas, background="#fff")
        left_window = left_canvas.create_window((0, 0), window=left_inner, anchor="nw")
        def _on_left_configure(event):
            left_canvas.configure(scrollregion=left_canvas.bbox("all"))
        left_inner.bind("<Configure>", _on_left_configure)
        left_canvas.bind("<Configure>", lambda e: left_canvas.itemconfig(left_window, width=e.width, height=e.height))
        left_canvas.config(width=scale_size(self.root, 350), height=1, bg="#fff")
        left_canvas.grid_propagate(False)
        left_canvas.bind_all("<MouseWheel>", lambda e: left_canvas.yview_scroll(int(-1*(e.delta/120)), "units"))
        self.setup_left(left_inner)

        # 中间：图传/状态/日志（Canvas+Scrollbar，自适应宽度）
        center_canvas = tk.Canvas(main_frame, bg=BG_COLOR, highlightthickness=0)
        center_scrollbar = ttk.Scrollbar(main_frame, orient="vertical", command=center_canvas.yview)
        center_canvas.grid(row=0, column=1, sticky="nsew")
        center_scrollbar.grid(row=0, column=1, sticky="nse")
        center_canvas.configure(yscrollcommand=center_scrollbar.set)
        center_inner = tk.Frame(center_canvas, background="#fff")
        center_window = center_canvas.create_window((0, 0), window=center_inner, anchor="nw")
        def _on_center_configure(event):
            center_canvas.configure(scrollregion=center_canvas.bbox("all"))
        center_inner.bind("<Configure>", _on_center_configure)
        center_canvas.bind("<Configure>", lambda e: center_canvas.itemconfig(center_window, width=e.width, height=e.height))
        center_canvas.config(bg="#fff")
        center_canvas.grid_propagate(False)
        center_canvas.bind_all("<MouseWheel>", lambda e: center_canvas.yview_scroll(int(-1*(e.delta/120)), "units"))
        self.setup_center(center_inner)

        # 右侧：云台遥感/追踪/激光（Canvas+Scrollbar，宽度固定可收缩）
        right_canvas = tk.Canvas(main_frame, bg=BG_COLOR, highlightthickness=0)
        right_scrollbar = ttk.Scrollbar(main_frame, orient="vertical", command=right_canvas.yview)
        right_canvas.grid(row=0, column=2, sticky="nsew")
        right_scrollbar.grid(row=0, column=2, sticky="nse")
        right_canvas.configure(yscrollcommand=right_scrollbar.set)
        right_inner = tk.Frame(right_canvas, background="#fff")
        right_window = right_canvas.create_window((0, 0), window=right_inner, anchor="nw")
        def _on_right_configure(event):
            right_canvas.configure(scrollregion=right_canvas.bbox("all"))
        right_inner.bind("<Configure>", _on_right_configure)
        right_canvas.bind("<Configure>", lambda e: right_canvas.itemconfig(right_window, width=e.width, height=e.height))
        right_canvas.config(width=scale_size(self.root, 370), height=1, bg="#fff")
        right_canvas.grid_propagate(False)
        right_canvas.bind_all("<MouseWheel>", lambda e: right_canvas.yview_scroll(int(-1*(e.delta/120)), "units"))
        self.setup_right(right_inner)

        # ttk主题美化
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("Main.TFrame", background=BG_COLOR)
        style.configure("Side.TFrame", background=BG_COLOR)
        style.configure("TLabel", background=BG_COLOR, foreground=FG_COLOR, font=font(BASE_SIZE))
        style.configure("Title.TLabel", font=font(BASE_SIZE+4, "bold"), foreground=PRIMARY_COLOR, background=BG_COLOR)
        style.configure("Section.TLabelframe", font=font(BASE_SIZE+1, "bold"), foreground=PRIMARY_COLOR, background=BG_COLOR, borderwidth=0, relief="flat")
        style.configure("Section.TLabelframe.Label", font=font(BASE_SIZE+1, "bold"), foreground=PRIMARY_COLOR, background=BG_COLOR)
        style.configure("TButton", font=font(BASE_SIZE, "bold"), foreground="white", background=PRIMARY_COLOR, borderwidth=0)
        style.map("TButton", background=[("active", SUCCESS_COLOR), ("disabled", DISABLED_COLOR)])
        style.configure("Accent.TLabel", foreground=ACCENT_COLOR, background=BG_COLOR, font=font(BASE_SIZE+1, "bold"))
        style.configure("Error.TLabel", foreground=ERROR_COLOR, background=BG_COLOR, font=font(BASE_SIZE+1, "bold"))
        style.configure("Success.TLabel", foreground=SUCCESS_COLOR, background=BG_COLOR, font=font(BASE_SIZE+1, "bold"))
        style.configure("Normal.TLabel", foreground="green", background=BG_COLOR, font=font(BASE_SIZE+1, "bold"))
        style.configure("Success.TButton", font=font(BASE_SIZE, "bold"), foreground="white", background=SUCCESS_COLOR, borderwidth=0)
        style.configure("Error.TButton", font=font(BASE_SIZE, "bold"), foreground="white", background=ERROR_COLOR, borderwidth=0)
        # 运动连接按钮两种状态
        style.configure("Connect.TButton", font=font(BASE_SIZE, "bold"), foreground="white", background=SUCCESS_COLOR, borderwidth=0)
        style.configure("Disconnect.TButton", font=font(BASE_SIZE, "bold"), foreground="white", background=DISABLED_COLOR, borderwidth=0)

        # 线程
        self.video_thread = threading.Thread(target=self.video_stream, daemon=True)
        self.video_thread.start()
        self.control_thread = threading.Thread(target=self.control_loop, daemon=True)
        self.control_thread.start()

        self.root.protocol("WM_DELETE_WINDOW", self.close_application)
        self.root.bind('<KeyPress>', self.on_key_press)
        self.root.focus_set()

        self.log("综合控制中心启动完成")
        self.log("请先确认串口并连接")

    # 追踪系统初始化
    def init_tracking_system(self):
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

    # 左侧区域
    def setup_left(self, parent):
        # 运动串口连接设置
        conn_frame = ttk.Labelframe(parent, text="🛠️ 运动串口", style="Section.TLabelframe")
        conn_frame.pack(fill=tk.X, padx=scale_size(self.root, 8), pady=(scale_size(self.root, 8), scale_size(self.root, 4)))
        for i in range(6):
            conn_frame.grid_columnconfigure(i, weight=1)
        self.motion_port_var = tk.StringVar()
        ports = self.get_serial_ports()
        ttk.Label(conn_frame, text="串口:", style="TLabel").grid(row=0, column=0, padx=(scale_size(self.root, 8),scale_size(self.root,2)), pady=scale_size(self.root,4), sticky="w")
        self.motion_port_combo = ttk.Combobox(conn_frame, textvariable=self.motion_port_var, values=ports, width=12)
        self.motion_port_combo.grid(row=0, column=1, padx=(0,scale_size(self.root,8)), pady=scale_size(self.root,4), sticky="w")
        self.motion_port_combo.bind("<Button-1>", lambda e: self.refresh_serial_ports(self.motion_port_combo))
        self.motion_confirm_btn = ttk.Button(conn_frame, text="确认选择", command=self.confirm_motion_port)
        self.motion_confirm_btn.grid(row=0, column=2, padx=scale_size(self.root,6), pady=scale_size(self.root,4), sticky="w")
        self.motion_connect_btn = ttk.Button(conn_frame, text="🔗 连接", command=self.toggle_motion_connection, state=tk.DISABLED, style="Connect.TButton")
        self.motion_connect_btn.grid(row=0, column=3, padx=scale_size(self.root,8), pady=scale_size(self.root,4), sticky="w")
        self.motion_confirm_info = ttk.Label(conn_frame, text="未确认", style="Accent.TLabel")
        self.motion_confirm_info.grid(row=1, column=0, columnspan=4, padx=scale_size(self.root,8), pady=(0,scale_size(self.root,4)), sticky="w")

        # 连接状态
        self.motion_status_label = ttk.Label(parent, text="● 未连接", style="Error.TLabel")
        self.motion_status_label.pack(anchor=tk.W, padx=scale_size(self.root,16), pady=(scale_size(self.root,2), scale_size(self.root,8)))

        # 推进器控制
        thruster_frame = ttk.Labelframe(parent, text="🌊 推进器控制", style="Section.TLabelframe")
        thruster_frame.pack(fill=tk.X, padx=scale_size(self.root,8), pady=scale_size(self.root,4))
        grid = ttk.Frame(thruster_frame)
        grid.pack(pady=scale_size(self.root,8))
        self.thruster_forward_btn = ttk.Button(grid, text="⬆\n前进", width=7)
        self.thruster_forward_btn.grid(row=0, column=1, padx=scale_size(self.root,4), pady=scale_size(self.root,4))
        self.setup_long_press(self.thruster_forward_btn, "WF", "推进器前进", "WS", "推进器停止", target="motion")
        self.thruster_left_btn = ttk.Button(grid, text="⬅\n左转", width=7)
        self.thruster_left_btn.grid(row=1, column=0, padx=scale_size(self.root,4), pady=scale_size(self.root,4))
        self.setup_long_press(self.thruster_left_btn, "WL", "推进器左转", "WS", "推进器停止", target="motion")
        self.thruster_stop_btn = ttk.Button(grid, text="⏹\n停止", width=7, command=lambda: self.send_command("WS", "推进器停止", target="motion"))
        self.thruster_stop_btn.grid(row=1, column=1, padx=scale_size(self.root,4), pady=scale_size(self.root,4))
        self.thruster_right_btn = ttk.Button(grid, text="➡\n右转", width=7)
        self.thruster_right_btn.grid(row=1, column=2, padx=scale_size(self.root,4), pady=scale_size(self.root,4))
        self.setup_long_press(self.thruster_right_btn, "WR", "推进器右转", "WS", "推进器停止", target="motion")

        # 履带控制
        track_frame = ttk.Labelframe(parent, text="🚂 履带控制", style="Section.TLabelframe")
        track_frame.pack(fill=tk.X, padx=scale_size(self.root,8), pady=scale_size(self.root,4))
        self.track_forward_btn = ttk.Button(track_frame, text="⬆\n前进", width=7)
        self.track_forward_btn.pack(pady=scale_size(self.root,4))
        self.setup_long_press(self.track_forward_btn, "TF", "履带前进", "TS", "履带停止", target="motion")

        ttk.Button(track_frame, text="⏹\n停止", width=7, command=lambda: self.send_command("TS", "履带停止", target="motion")).pack(pady=scale_size(self.root,4))

        self.track_backward_btn = ttk.Button(track_frame, text="⬇\n后退", width=7)
        self.track_backward_btn.pack(pady=scale_size(self.root,4))
        self.setup_long_press(self.track_backward_btn, "TB", "履带后退", "TS", "履带停止", target="motion")

        # 特殊功能
        special_frame = ttk.Labelframe(parent, text="⚙️ 特殊功能", style="Section.TLabelframe")
        special_frame.pack(fill=tk.X, padx=scale_size(self.root,8), pady=scale_size(self.root,4))
        ttk.Button(special_frame, text="🔓 解锁电调", command=lambda: self.send_command("UNLOCK", "解锁电调", target="motion")).pack(side=tk.LEFT, padx=scale_size(self.root,6), pady=scale_size(self.root,8))
        ttk.Button(special_frame, text="🔄 软件复位", command=self.software_reset).pack(side=tk.LEFT, padx=scale_size(self.root,6), pady=scale_size(self.root,8))
        ttk.Button(special_frame, text="🛑 紧急停止", command=self.emergency_stop).pack(side=tk.LEFT, padx=scale_size(self.root,6), pady=scale_size(self.root,8))

    def confirm_motion_port(self):
        self.motion_confirmed_port = self.motion_port_var.get().strip()
        self.motion_confirmed_baud = "115200"
        self.motion_confirm_info.config(text=f"已确认: {self.motion_confirmed_port}@115200")
        self.motion_connect_btn.config(state=tk.NORMAL)

    # 中间区域
    def setup_center(self, parent):
        ttk.Label(parent, text="📹 实时图传", style="Title.TLabel").pack(pady=(scale_size(self.root,10), scale_size(self.root,6)), anchor="w")
        self.video_label = ttk.Label(parent, background=BG_COLOR)
        self.video_label.pack(fill=tk.BOTH, expand=False, padx=scale_size(self.root,10), pady=(0, scale_size(self.root,10)))
        status_frame = ttk.Labelframe(parent, text="📊 系统状态", style="Section.TLabelframe")
        status_frame.pack(fill=tk.X, padx=scale_size(self.root,10), pady=(scale_size(self.root,10), 0))
        self.status_text = ttk.Label(status_frame, text="串口/摄像头/云台状态", style="Accent.TLabel", anchor="w")
        self.status_text.pack(fill=tk.X, padx=scale_size(self.root,6), pady=scale_size(self.root,6))
        log_frame = ttk.Labelframe(parent, text="📝 日志", style="Section.TLabelframe")
        log_frame.pack(fill=tk.BOTH, expand=True, padx=scale_size(self.root,10), pady=scale_size(self.root,10))
        # 使用 ttk.Frame 包裹 tk.Text，避免 fg 参数，前景色通过 insertbackground 设置
        self.log_text_frame = ttk.Frame(log_frame)
        self.log_text_frame.pack(fill=tk.BOTH, expand=True)
        self.log_text = tk.Text(self.log_text_frame, height=12, font=('Consolas', scale_size(self.root,10)),
                                bg=BG_COLOR, insertbackground=PRIMARY_COLOR, selectbackground=PRIMARY_COLOR,
                                wrap=tk.WORD, state=tk.DISABLED, relief=tk.FLAT, bd=0)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        self.target_label = ttk.Label(status_frame, text="目标: 未检测", style="Accent.TLabel")
        self.target_label.pack(anchor="w", padx=scale_size(self.root,6), pady=(0, scale_size(self.root,2)))
        self.angle_label_center = ttk.Label(status_frame, text="角度: 135°, 90°", style="Success.TLabel")
        self.angle_label_center.pack(anchor="w", padx=scale_size(self.root,6), pady=(0, scale_size(self.root,2)))

    # 右侧区域
    def setup_right(self, parent):
        ttk.Label(parent, text="云台与功能", style="Title.TLabel").pack(pady=(scale_size(self.root,10), scale_size(self.root,10)))
        # 云台串口连接设置
        gimbal_conn_frame = ttk.Labelframe(parent, text="🛠️ 云台串口", style="Section.TLabelframe")
        gimbal_conn_frame.pack(fill=tk.X, padx=scale_size(self.root,10), pady=(0, scale_size(self.root,8)))
        for i in range(6):
            gimbal_conn_frame.grid_columnconfigure(i, weight=1)
        self.gimbal_port_var = tk.StringVar()
        ports = self.get_serial_ports()
        ttk.Label(gimbal_conn_frame, text="串口:", style="TLabel").grid(row=0, column=0, padx=(scale_size(self.root,8),scale_size(self.root,2)), pady=scale_size(self.root,4), sticky="w")
        self.gimbal_port_combo = ttk.Combobox(gimbal_conn_frame, textvariable=self.gimbal_port_var, values=ports, width=12)
        self.gimbal_port_combo.grid(row=0, column=1, padx=(0,scale_size(self.root,8)), pady=scale_size(self.root,4), sticky="w")
        self.gimbal_port_combo.bind("<Button-1>", lambda e: self.refresh_serial_ports(self.gimbal_port_combo))
        self.gimbal_confirm_btn = ttk.Button(gimbal_conn_frame, text="确认选择", command=self.confirm_gimbal_port)
        self.gimbal_confirm_btn.grid(row=0, column=2, padx=scale_size(self.root,6), pady=scale_size(self.root,4), sticky="w")
        self.gimbal_connect_btn = ttk.Button(gimbal_conn_frame, text="🔗 连接", command=self.toggle_gimbal_connection, state=tk.DISABLED)
        self.gimbal_connect_btn.grid(row=0, column=3, padx=scale_size(self.root,8), pady=scale_size(self.root,4), sticky="w")
        self.gimbal_confirm_info = ttk.Label(gimbal_conn_frame, text="未确认", style="Accent.TLabel")
        self.gimbal_confirm_info.grid(row=1, column=0, columnspan=4, padx=scale_size(self.root,8), pady=(0,scale_size(self.root,4)), sticky="w")
        self.gimbal_status_label = ttk.Label(parent, text="● 未连接", style="Error.TLabel")
        self.gimbal_status_label.pack(anchor=tk.W, padx=scale_size(self.root,16), pady=(scale_size(self.root,2), scale_size(self.root,8)))

        joystick_frame = ttk.Labelframe(parent, text="🕹️ 云台遥感", style="Section.TLabelframe")
        joystick_frame.pack(fill=tk.X, padx=scale_size(self.root,10), pady=scale_size(self.root,8))
        self.joystick_canvas = tk.Canvas(joystick_frame, width=JOYSTICK_SIZE, height=JOYSTICK_SIZE, bg=BG_COLOR, highlightthickness=0, bd=0)
        self.joystick_canvas.pack(pady=scale_size(self.root,10))
        self.joystick_canvas.bind("<Button-1>", self.joystick_press)
        self.joystick_canvas.bind("<B1-Motion>", self.joystick_drag)
        self.joystick_canvas.bind("<ButtonRelease-1>", self.joystick_release)
        self.draw_joystick()
        ttk.Button(parent, text="📍 云台归中", command=self.center_camera).pack(fill=tk.X, padx=scale_size(self.root,18), pady=(scale_size(self.root,10), scale_size(self.root,6)))
        self.tracking_button = ttk.Button(parent, text="🔴 开启追踪", command=self.toggle_tracking)
        self.tracking_button.pack(fill=tk.X, padx=scale_size(self.root,18), pady=(0, scale_size(self.root,6)))
        self.laser_button = ttk.Button(parent, text="🔴 发射激光", command=self.fire_laser)
        self.laser_button.pack(fill=tk.X, padx=scale_size(self.root,18), pady=(0, scale_size(self.root,6)))
        self.angle_label = ttk.Label(parent, text="角度: 135°, 90°", style="Success.TLabel")
        self.angle_label.pack(pady=(scale_size(self.root,10), 0))

    def confirm_gimbal_port(self):
        self.gimbal_confirmed_port = self.gimbal_port_var.get().strip()
        self.gimbal_confirmed_baud = "115200"
        self.gimbal_confirm_info.config(text=f"已确认: {self.gimbal_confirmed_port}@115200")
        self.gimbal_connect_btn.config(state=tk.NORMAL)

    # 串口相关
    def get_serial_ports(self):
        try:
            ports = serial.tools.list_ports.comports()
            return [port.device for port in ports]
        except Exception:
            return []

    def refresh_serial_ports(self, combo):
        ports = self.get_serial_ports()
        combo['values'] = ports
        var = combo.cget('textvariable')
        if ports:
            v = self.root.getvar(var)
            if v not in ports:
                self.root.setvar(var, ports[0])

    def toggle_motion_connection(self):
        if self.motion_ser:
            try:
                self.motion_ser.close()
            except Exception:
                pass
            self.motion_ser = None
            self.motion_connect_btn.config(text="🔗 连接", style="Connect.TButton")
            self.motion_status_label.config(text="● 未连接", style="Error.TLabel")
            self.log("运动串口已断开")
        else:
            port = self.motion_confirmed_port
            try:
                baudrate = int(self.motion_confirmed_baud)
            except ValueError:
                messagebox.showerror("错误", "波特率必须为数字")
                return
            try:
                self.motion_ser = serial.Serial(port, baudrate, timeout=1)
                self.motion_connect_btn.config(text="⛔ 断开", style="Disconnect.TButton")
                self.motion_status_label.config(text="● 已连接", style="Success.TLabel")
                self.log(f"运动串口连接成功: {port}@{baudrate}")
            except Exception as e:
                self.motion_ser = None
                self.motion_connect_btn.config(text="🔗 连接", style="Connect.TButton")
                self.motion_status_label.config(text="● 未连接", style="Error.TLabel")
                messagebox.showerror("连接失败", f"无法连接到运动串口: {e}")
                self.log(f"运动串口连接失败: {e}")

    def toggle_gimbal_connection(self):
        if self.gimbal_ser:
            try:
                self.gimbal_ser.close()
            except Exception:
                pass
            self.gimbal_ser = None
            self.gimbal_connect_btn.config(text="🔗 连接", style="Success.TButton")
            self.gimbal_status_label.config(text="● 未连接", style="Error.TLabel")
            self.log("云台串口已断开")
        else:
            port = self.gimbal_confirmed_port
            try:
                baudrate = int(self.gimbal_confirmed_baud)
            except ValueError:
                messagebox.showerror("错误", "波特率必须为数字")
                return
            try:
                self.gimbal_ser = serial.Serial(port, baudrate, timeout=1)
                self.gimbal_connect_btn.config(text="🔌 断开", style="Error.TButton")
                self.gimbal_status_label.config(text="● 已连接", style="Success.TLabel")
                self.log(f"云台串口连接成功: {port}@{baudrate}")
            except Exception as e:
                self.gimbal_ser = None
                self.gimbal_connect_btn.config(text="🔗 连接", style="Success.TButton")
                self.gimbal_status_label.config(text="● 未连接", style="Error.TLabel")
                messagebox.showerror("连接失败", f"无法连接到云台串口: {e}")
                self.log(f"云台串口连接失败: {e}")

    # 控制命令
    def send_command(self, command, description, target="motion"):
        ser = self.motion_ser if target == "motion" else self.gimbal_ser
        if ser:
            try:
                msg = command.strip() + '\n'
                ser.write(msg.encode('utf-8'))
                self.log(f"发送命令: {command} ({description})")
                return True
            except Exception as e:
                self.log(f"串口发送失败: {e}")
                return False
        else:
            self.log(f"发送失败: {command} ({description}) - 串口未连接")
            return False

    def emergency_stop(self):
        self.log("🛑 执行紧急停止!")
        self.send_command("TS", "履带停止", target="motion")
        self.send_command("WS", "推进器停止", target="motion")

    def software_reset(self):
        result = messagebox.askyesno("确认复位", "确定要执行软件复位吗？\n\n这将重启STM32控制器，所有设备将停止工作。", icon='warning')
        if result:
            self.log("🔄 执行软件复位...")
            if self.send_command("RESET", "软件复位", target="motion"):
                self.log("软件复位命令已发送")
            else:
                self.log("软件复位失败: 串口未连接")
                messagebox.showerror("错误", "软件复位失败：串口未连接")

    # 推进器/履带长按
    def setup_long_press(self, button, press_command, press_desc, release_command, release_desc, target="motion"):
        button.press_command = press_command
        button.press_desc = press_desc
        button.release_command = release_command
        button.release_desc = release_desc
        button.target = target
        button.is_pressed = False
        button.bind("<ButtonPress-1>", lambda e: self.on_button_press(button))
        button.bind("<ButtonRelease-1>", lambda e: self.on_button_release(button))
        button.bind("<Leave>", lambda e: self.on_button_release(button))

    def on_button_press(self, button):
        if not button.is_pressed:
            button.is_pressed = True
            self.send_command(button.press_command, button.press_desc, target=button.target)

    def on_button_release(self, button):
        if button.is_pressed:
            button.is_pressed = False
            self.send_command(button.release_command, button.release_desc, target=button.target)
            button.config(style="TButton")

    # 云台遥感
    def draw_joystick(self):
        self.joystick_canvas.delete("all")
        cx, cy = JOYSTICK_SIZE // 2, JOYSTICK_SIZE // 2
        outer = JOYSTICK_OUTER_RADIUS
        inner = JOYSTICK_INNER_RADIUS
        self.joystick_canvas.create_oval(cx - outer, cy - outer, cx + outer, cy + outer, outline=GRAY_COLOR, width=JOYSTICK_LINE_WIDTH, fill=SECONDARY_COLOR)
        self.joystick_canvas.create_line(cx - outer + 12, cy, cx + outer - 12, cy, fill=PRIMARY_COLOR, width=2)
        self.joystick_canvas.create_line(cx, cy - outer + 12, cx, cy + outer - 12, fill=PRIMARY_COLOR, width=2)
        # emoji兼容字体
        label_font = (EMOJI_FONT, scale_size(self.root, 11), "bold")
        self.joystick_canvas.create_text(cx, cy - outer - JOYSTICK_LABEL_OFFSET, text="上", fill=FG_COLOR, font=label_font)
        self.joystick_canvas.create_text(cx, cy + outer + JOYSTICK_LABEL_OFFSET, text="下", fill=FG_COLOR, font=label_font)
        self.joystick_canvas.create_text(cx - outer - JOYSTICK_LABEL_OFFSET, cy, text="左", fill=FG_COLOR, font=label_font)
        self.joystick_canvas.create_text(cx + outer + JOYSTICK_LABEL_OFFSET, cy, text="右", fill=FG_COLOR, font=label_font)
        if self.joystick_active:
            ix = cx - self.joystick_x * (outer - inner)
            iy = cy + self.joystick_y * (outer - inner)
            color = ACCENT_COLOR
        else:
            ix, iy = cx, cy
            color = SUCCESS_COLOR
        self.joystick_canvas.create_oval(ix - inner, iy - inner, ix + inner, iy + inner, outline=FG_COLOR, width=JOYSTICK_DOT_WIDTH, fill=color)
        coord_text = f"X:{self.joystick_x:.2f}, Y:{self.joystick_y:.2f}"
        coord_font = (FONT_FAMILIES, scale_size(self.root, 10))
        self.joystick_canvas.create_text(cx, cy + outer + JOYSTICK_COORD_OFFSET, text=coord_text, fill=FG_COLOR, font=coord_font)

    def joystick_press(self, event):
        self.joystick_active = True
        self.update_joystick_position(event.x, event.y)

    def joystick_drag(self, event):
        if self.joystick_active:
            self.update_joystick_position(event.x, event.y)

    def joystick_release(self, event):
        self.joystick_active = False
        self.joystick_x = 0
        self.joystick_y = 0
        self.draw_joystick()

    def update_joystick_position(self, mx, my):
        cx, cy = JOYSTICK_SIZE // 2, JOYSTICK_SIZE // 2
        max_r = JOYSTICK_OUTER_RADIUS - JOYSTICK_INNER_RADIUS - 6
        dx = mx - cx
        dy = my - cy
        dist = math.sqrt(dx*dx + dy*dy)
        if dist > max_r:
            dx = dx * max_r / dist
            dy = dy * max_r / dist
        self.joystick_x = -dx / max_r
        self.joystick_y = dy / max_r
        self.draw_joystick()

    def control_loop(self):
        while self.running:
            if self.gimbal_ser and self.joystick_active and not self.tracking_mode:
                pan_delta = self.joystick_x * 2.0
                tilt_delta = self.joystick_y * 1.5
                self.pan_angle += pan_delta
                self.tilt_angle += tilt_delta
                self.pan_angle = max(0, min(270, self.pan_angle))
                self.tilt_angle = max(0, min(180, self.tilt_angle))
                self.send_gimbal_cmd(self.pan_angle, self.tilt_angle)
                self.angle_label.config(text=f"角度: {self.pan_angle:.0f}°, {self.tilt_angle:.0f}°")
                self.angle_label_center.config(text=f"角度: {self.pan_angle:.0f}°, {self.tilt_angle:.0f}°")
            time.sleep(0.05)

    def send_gimbal_cmd(self, pan, tilt, trigger=0):
        if self.gimbal_ser:
            try:
                pan_int = int(pan) & 0xFFFF
                tilt_int = int(tilt) & 0xFFFF
                data = bytes([
                    (pan_int >> 8) & 0xFF,
                    pan_int & 0xFF,
                    (tilt_int >> 8) & 0xFF,
                    tilt_int & 0xFF,
                    trigger
                ])
                self.gimbal_ser.write(data)
            except Exception as e:
                self.log(f"云台命令发送失败: {e}")

    def toggle_tracking(self):
        self.tracking_mode = not self.tracking_mode
        if self.tracking_mode:
            self.tracking_button.configure(text="🟢 关闭追踪")
            self.log("追踪模式已开启")
        else:
            self.tracking_button.configure(text="🔴 开启追踪")
            self.log("追踪模式已关闭")
            self.trigger_counter = 0
            self.stable_frames = 0
            self.stability_history.clear()

    def fire_laser(self):
        if self.laser_firing or not self.gimbal_ser:
            return
        self.laser_firing = True
        self.laser_button.configure(text="🔥 发射中...", state='disabled')
        try:
            pan_int = int(self.pan_angle) & 0xFFFF
            tilt_int = int(self.tilt_angle) & 0xFFFF
            data = bytes([
                (pan_int >> 8) & 0xFF,
                pan_int & 0xFF,
                (tilt_int >> 8) & 0xFF,
                tilt_int & 0xFF,
                2
            ])
            self.gimbal_ser.write(data)
            self.log("激光发射命令已发送")
        except Exception as e:
            self.log(f"激光命令发送失败: {e}")
        self.root.after(2000, self.laser_finished)

    def laser_finished(self):
        self.laser_firing = False
        self.laser_button.configure(text="🔴 发射激光", state='normal')

    def center_camera(self):
        if not self.tracking_mode:
            self.pan_angle = 135
            self.tilt_angle = 90
            self.send_gimbal_cmd(135, 90)
            self.angle_label.config(text="角度: 135°, 90°")
            self.angle_label_center.config(text="角度: 135°, 90°")
            self.log("云台归中")

    # 视频流
    def video_stream(self):
        self.cap = cv2.VideoCapture(1, cv2.CAP_V4L2)
        if not self.cap.isOpened():
            self.log("无法打开摄像头")
            return
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.cap.set(cv2.CAP_PROP_FPS, 30)
        frame_count = 0
        start_time = time.time()
        while self.running and self.cap:
            ret, frame = self.cap.read()
            if not ret:
                continue
            frame_count += 1
            if self.tracking_mode:
                frame = self.process_tracking(frame)
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frame_pil = Image.fromarray(frame_rgb)
            frame_pil = frame_pil.resize((640, 480), Image.Resampling.LANCZOS)
            frame_tk = ImageTk.PhotoImage(frame_pil)
            self.video_label.configure(image=frame_tk)
            self.video_label.image = frame_tk
            if frame_count % 30 == 0:
                elapsed = time.time() - start_time
                fps = frame_count / elapsed
                self.status_text.config(text=f"FPS: {fps:.1f}")
                frame_count = 0
                start_time = time.time()
            time.sleep(0.033)

    # 追踪处理
    def process_tracking(self, frame):
        height, width = frame.shape[:2]
        center_x, center_y = width // 2, height // 2
        cv2.line(frame, (center_x-15, center_y), (center_x+15, center_y), (0, 255, 0), 2)
        cv2.line(frame, (center_x, center_y-15), (center_x, center_y+15), (0, 255, 0), 2)
        cv2.circle(frame, (center_x, center_y), self.CENTER_TOLERANCE, (0, 255, 0), 1)
        x, y, radius = self.detect_red_target(frame)
        trigger = False
        if x is not None:
            self.x_filter.add(x)
            self.y_filter.add(y)
            filtered_x = self.x_filter.get_filtered()
            filtered_y = self.y_filter.get_filtered()
            if filtered_x is not None and filtered_y is not None:
                error_x = (filtered_x - center_x) / center_x
                error_y = (filtered_y - center_y) / center_y
                pan_output = self.pan_pid.compute(error_x)
                tilt_output = self.tilt_pid.compute(error_y)
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
                target_pan = 135 - pan_output * control_strength_pan
                target_tilt = 90 + tilt_output * control_strength_tilt
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
                    self.angle_label.config(text=f"角度: {self.pan_angle:.0f}°, {self.tilt_angle:.0f}°")
                    self.angle_label_center.config(text=f"角度: {self.pan_angle:.0f}°, {self.tilt_angle:.0f}°")
                self.stability_history.append(distance)
                if len(self.stability_history) >= 5:
                    recent_distances = list(self.stability_history)[-5:]
                    distance_variance = np.var(recent_distances)
                    if distance_variance < 2.0:
                        self.stable_frames += 1
                    else:
                        self.stable_frames = 0
                if (abs(error_x) < self.TRIGGER_THRESHOLD and 
                    abs(error_y) < self.TRIGGER_THRESHOLD and 
                    radius > 20 and
                    self.stable_frames > 5):
                    self.trigger_counter += 1
                    if self.trigger_counter >= self.TRIGGER_DELAY:
                        trigger = True
                else:
                    self.trigger_counter = max(0, self.trigger_counter - 1)
                color = (0, 255, 0) if distance <= self.CENTER_TOLERANCE else (0, 0, 255)
                cv2.circle(frame, (int(filtered_x), int(filtered_y)), int(radius), color, 2)
                cv2.circle(frame, (int(filtered_x), int(filtered_y)), 3, color, -1)
                cv2.line(frame, (int(filtered_x), int(filtered_y)), (center_x, center_y), (255, 255, 0), 1)
                cv2.putText(frame, f"Distance: {distance:.1f}px", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)
                if trigger:
                    cv2.putText(frame, "TARGET LOCKED!", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
                self.target_label.config(text=f"目标: 距离{distance:.1f}px")
            self.send_gimbal_cmd(self.pan_angle, self.tilt_angle, 1 if trigger else 0)
        else:
            self.trigger_counter = 0
            self.stable_frames = 0
            self.stability_history.clear()
            self.target_label.config(text="目标: 未检测")
            self.send_gimbal_cmd(self.pan_angle, self.tilt_angle, 0)
        return frame

    def detect_red_target(self, frame):
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
        diff = new_angle - last_angle
        if abs(diff) < self.DEAD_ZONE:
            return last_angle
        if abs(diff) > self.MAX_ANGLE_CHANGE:
            return last_angle + (self.MAX_ANGLE_CHANGE if diff > 0 else -self.MAX_ANGLE_CHANGE)
        return new_angle

    # 日志
    def log(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_message = f"[{timestamp}] {message}\n"
        self.log_lines.append(log_message)
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        self.log_text.insert(tk.END, ''.join(self.log_lines))
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

    # 键盘快捷键
    def on_key_press(self, event):
        key = event.char.lower()
        if key == 'w':
            self.send_command("TF", "履带前进", target="motion")
        elif key == 's':
            self.send_command("TB", "履带后退", target="motion")
        elif key == 'j':
            self.send_command("TS", "履带停止", target="motion")
        elif key == 'a':
            self.send_command("WL", "推进器左转", target="motion")
        elif key == 'd':
            self.send_command("WR", "推进器右转", target="motion")
        elif key == 'i':
            self.send_command("WF", "推进器前进", target="motion")
        elif key == 'k':
            self.send_command("WS", "推进器停止", target="motion")
        elif key == 'u':
            self.send_command("UNLOCK", "解锁电调", target="motion")
        elif key == 'r':
            self.software_reset()
        elif key == ' ':
            self.emergency_stop()

    def close_application(self):
        self.running = False
        if self.cap:
            self.cap.release()
        if self.motion_ser:
            self.motion_ser.close()
        if self.gimbal_ser:
            self.gimbal_ser.close()
        self.root.quit()
    def update_widget_scale(self, widget=None):
        if widget is None:
            widget = self.root
        # 字体缩放
        try:
            current_font = widget.cget("font")
            if current_font:
                size = int(BASE_SIZE * self.scale_factor)
                widget.configure(font=(FONT_FAMILIES, size))
        except Exception:
            pass
        # Canvas特殊处理
        if isinstance(widget, tk.Canvas):
            try:
                w = int(widget.winfo_reqwidth() * self.scale_factor)
                h = int(widget.winfo_reqheight() * self.scale_factor)
                widget.config(width=w, height=h)
            except Exception:
                pass
        # 递归子控件
        for child in widget.winfo_children():
            self.update_widget_scale(child)

# 删除类外部的on_window_resize定义，避免与类内方法冲突

    def run(self):
        self.root.mainloop()

    def on_window_resize(self, event):
        # 只在主窗口变化时响应
        if event.widget == self.root:
            w, h = event.width, event.height
            scale_w = w / self.base_width
            scale_h = h / self.base_height
            self.scale_factor = min(scale_w, scale_h)
            # 动态调整ttk.Style字体和按钮样式
            style = ttk.Style(self.root)
            size = max(8, int(BASE_SIZE * self.scale_factor))
            btn_ipadx = int(16 * self.scale_factor)
            btn_ipady = int(8 * self.scale_factor)
            btn_padx = int(8 * self.scale_factor)
            btn_pady = int(6 * self.scale_factor)
            style.configure("TLabel", font=(FONT_FAMILIES, size))
            style.configure("Title.TLabel", font=(FONT_FAMILIES, size+4, "bold"))
            style.configure("Section.TLabelframe", font=(FONT_FAMILIES, size+1, "bold"))
            style.configure("Section.TLabelframe.Label", font=(FONT_FAMILIES, size+1, "bold"))
            style.configure("TButton", font=(FONT_FAMILIES, size, "bold"), padding=(btn_ipadx, btn_ipady))
            style.configure("Accent.TLabel", font=(FONT_FAMILIES, size+1, "bold"))
            style.configure("Error.TLabel", font=(FONT_FAMILIES, size+1, "bold"))
            style.configure("Success.TLabel", font=(FONT_FAMILIES, size+1, "bold"))
            style.configure("Normal.TLabel", font=(FONT_FAMILIES, size+1, "bold"))
            style.configure("Success.TButton", font=(FONT_FAMILIES, size, "bold"), padding=(btn_ipadx, btn_ipady))
            style.configure("Error.TButton", font=(FONT_FAMILIES, size, "bold"), padding=(btn_ipadx, btn_ipady))
            style.configure("Connect.TButton", font=(FONT_FAMILIES, size, "bold"), padding=(btn_ipadx, btn_ipady))
            style.configure("Disconnect.TButton", font=(FONT_FAMILIES, size, "bold"), padding=(btn_ipadx, btn_ipady))
            # 居中主内容Frame
            offset_x = int((w - self.base_width * self.scale_factor) / 2)
            offset_y = int((h - self.base_height * self.scale_factor) / 2)
            self.main_frame.place(x=offset_x, y=offset_y,
                                 width=int(self.base_width * self.scale_factor),
                                 height=int(self.base_height * self.scale_factor))
            # 递归调整所有按钮的padx/pady
            def update_button_padding(widget):
                for child in widget.winfo_children():
                    if isinstance(child, ttk.Button):
                        child.configure(padding=(btn_padx, btn_pady))
                    update_button_padding(child)
            update_button_padding(self.main_frame)
            # 动态调整摇杆Canvas尺寸并重绘
            if hasattr(self, "joystick_canvas"):
                joy_size = max(120, int(220 * self.scale_factor))
                self.joystick_canvas.config(width=joy_size, height=joy_size)
                self.draw_joystick()
            self.update_widget_scale()

if __name__ == "__main__":
    app = MergedControlUI()
    app.run()