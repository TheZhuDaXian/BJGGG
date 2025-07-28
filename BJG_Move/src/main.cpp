#include <Arduino.h>
#include <Servo.h>

// 推进器
Servo leftThruster;
Servo rightThruster;

// 履带与推进器相关宏定义
#define TRACK_FL_PWM PA0   // 前左履带PWM
#define TRACK_FL_DIR1 PA1  // 前左履带方向1
#define TRACK_FL_DIR2 PA4  // 前左履带方向2
#define TRACK_FR_PWM PA5   // 前右履带PWM
#define TRACK_FR_DIR1 PA6  // 前右履带方向1
#define TRACK_FR_DIR2 PA7  // 前右履带方向2
#define TRACK_BL_PWM PB6   // 后左履带PWM
#define TRACK_BL_DIR1 PB7  // 后左履带方向1
#define TRACK_BL_DIR2 PB8  // 后左履带方向2
#define TRACK_BR_PWM PB9   // 后右履带PWM
#define TRACK_BR_DIR1 PB10 // 后右履带方向1
#define TRACK_BR_DIR2 PB11 // 后右履带方向2
#define TRACK_STBY1 PC14   // TB6612FNG使能1
#define TRACK_STBY2 PC15   // TB6612FNG使能2
#define LEFT_THRUSTER_PIN PB0
#define RIGHT_THRUSTER_PIN PB1
#define ESC_STOP 1050
#define ESC_MAX 2000
#define TRACK_PWM_MAX 128
#define TRACK_PWM_TURN 40   // 转向履带速度
#define LEFT_THRUSTER_OFFSET 0
#define RIGHT_THRUSTER_OFFSET 0
#define LED_PIN PC13

const int SOFT_PWM_PERIOD = 2000;

int soft_pwm_fl_speed = 0, soft_pwm_fr_speed = 0, soft_pwm_bl_speed = 0, soft_pwm_br_speed = 0;
bool soft_pwm_fl_forward = true, soft_pwm_fr_forward = true, soft_pwm_bl_forward = true, soft_pwm_br_forward = true;
bool thrusterActive = false;
bool trackActive = false;
int currentLeftThrust = ESC_STOP;
int currentRightThrust = ESC_STOP;

// 函数声明
void processCommand(String cmd);
void setThruster(int left, int right);
void setTrackMotorSoftPWM(int track_id, int speed, bool forward); // 0:FL 1:FR 2:BL 3:BR
void stopAllTracks();
void ledBlink(int times, int delayMs);

void setup() {
  // 初始化串口 - 使用Serial2 (PA2/PA3)
  Serial2.begin(115200);
  
  // 备用串口调试 - 如果Serial2不工作，可以尝试Serial1
  // Serial1.begin(115200);  // PA9/PA10
  
  // 初始化LED
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, HIGH);
  
  // 启动调试信息
  delay(1000);  // 等待串口稳定
  Serial2.println("=== STM32启动 ===");
  Serial2.println("履带控制系统v1.0");
  Serial2.print("编译时间: ");
  Serial2.print(__DATE__);
  Serial2.print(" ");
  Serial2.println(__TIME__);
  Serial2.println("等待命令...");
  Serial2.println("================");
  
  // 初始化电调
  delay(500); // 上电后延迟，等电调完全启动
  leftThruster.attach(LEFT_THRUSTER_PIN);
  rightThruster.attach(RIGHT_THRUSTER_PIN);
  setThruster(ESC_STOP, ESC_STOP); // 立即发送停止信号
  
  // 初始化履带引脚（两个TB6612FNG模块）
  // 第一个TB6612FNG - 前履带
  pinMode(TRACK_FL_PWM, OUTPUT);
  pinMode(TRACK_FL_DIR1, OUTPUT);
  pinMode(TRACK_FL_DIR2, OUTPUT);
  pinMode(TRACK_FR_PWM, OUTPUT);
  pinMode(TRACK_FR_DIR1, OUTPUT);
  pinMode(TRACK_FR_DIR2, OUTPUT);
  pinMode(TRACK_STBY1, OUTPUT);
  
  // 第二个TB6612FNG - 后履带
  pinMode(TRACK_BL_PWM, OUTPUT);
  pinMode(TRACK_BL_DIR1, OUTPUT);
  pinMode(TRACK_BL_DIR2, OUTPUT);
  pinMode(TRACK_BR_PWM, OUTPUT);
  pinMode(TRACK_BR_DIR1, OUTPUT);
  pinMode(TRACK_BR_DIR2, OUTPUT);
  pinMode(TRACK_STBY2, OUTPUT);
  
  // 使能两个TB6612FNG模块
  digitalWrite(TRACK_STBY1, HIGH);
  digitalWrite(TRACK_STBY2, HIGH);
  
  
  // 启动完成指示
  Serial2.println("系统初始化完成!");
  Serial2.println("等待MQTT命令...");
}

void loop() {
  // 心跳信号 - 每5秒发送一次状态
  static unsigned long lastHeartbeat = 0;
  if (millis() - lastHeartbeat > 5000) {
    Serial2.println("[心跳] STM32运行正常，等待命令...");
    lastHeartbeat = millis();
  }
  
  while (Serial2.available()) {
    String cmd = Serial2.readStringUntil('\n');
    cmd.trim();
    
    if (cmd.length() > 0) {
      Serial2.print("RX: ");
      Serial2.println(cmd);
      processCommand(cmd);
    }
    
    while (Serial2.available()) {
      Serial2.read();
    }
  }
  
  // 电调保活机制 - 缩短保活间隔，确保电调不上锁
  static unsigned long lastKeep = 0;
  if (millis() - lastKeep > 50) {  // 改为50ms，更频繁的保活
    if (thrusterActive) {
      // 推进器活动时持续发送当前状态
      setThruster(currentLeftThrust, currentRightThrust);
    } else {
      // 推进器停止时必须持续发送停止信号保活
      // 无论履带状态如何，都要保持电调信号
      setThruster(ESC_STOP, ESC_STOP);
    }
    lastKeep = millis();
  }
  
  // 软件PWM输出（四路履带）
  unsigned long now = micros();
  static bool pwm_fl_state = false, pwm_fr_state = false, pwm_bl_state = false, pwm_br_state = false;
  static unsigned long pwm_fl_start = 0, pwm_fr_start = 0, pwm_bl_start = 0, pwm_br_start = 0;

  // 前左
  int duty_fl = soft_pwm_fl_speed;
  if (duty_fl > 255) duty_fl = 255;
  if (duty_fl < 0) duty_fl = 0;
  int high_fl = SOFT_PWM_PERIOD * duty_fl / 255;
  int low_fl = SOFT_PWM_PERIOD - high_fl;
  if (soft_pwm_fl_forward) {
    digitalWrite(TRACK_FL_DIR1, HIGH); digitalWrite(TRACK_FL_DIR2, LOW);
  } else {
    digitalWrite(TRACK_FL_DIR1, LOW); digitalWrite(TRACK_FL_DIR2, HIGH);
  }
  if (duty_fl > 0) {
    if (!pwm_fl_state && (now - pwm_fl_start >= low_fl)) {
      digitalWrite(TRACK_FL_PWM, HIGH);
      pwm_fl_state = true;
      pwm_fl_start = now;
    }
    if (pwm_fl_state && (now - pwm_fl_start >= high_fl)) {
      digitalWrite(TRACK_FL_PWM, LOW);
      pwm_fl_state = false;
      pwm_fl_start = now;
    }
  } else {
    digitalWrite(TRACK_FL_PWM, LOW);
    pwm_fl_state = false;
    pwm_fl_start = now;
  }

  // 前右
  int duty_fr = soft_pwm_fr_speed;
  if (duty_fr > 255) duty_fr = 255;
  if (duty_fr < 0) duty_fr = 0;
  int high_fr = SOFT_PWM_PERIOD * duty_fr / 255;
  int low_fr = SOFT_PWM_PERIOD - high_fr;
  if (soft_pwm_fr_forward) {
    digitalWrite(TRACK_FR_DIR1, HIGH); digitalWrite(TRACK_FR_DIR2, LOW);
  } else {
    digitalWrite(TRACK_FR_DIR1, LOW); digitalWrite(TRACK_FR_DIR2, HIGH);
  }
  if (duty_fr > 0) {
    if (!pwm_fr_state && (now - pwm_fr_start >= low_fr)) {
      digitalWrite(TRACK_FR_PWM, HIGH);
      pwm_fr_state = true;
      pwm_fr_start = now;
    }
    if (pwm_fr_state && (now - pwm_fr_start >= high_fr)) {
      digitalWrite(TRACK_FR_PWM, LOW);
      pwm_fr_state = false;
      pwm_fr_start = now;
    }
  } else {
    digitalWrite(TRACK_FR_PWM, LOW);
    pwm_fr_state = false;
    pwm_fr_start = now;
  }

  // 后左
  int duty_bl = soft_pwm_bl_speed;
  if (duty_bl > 255) duty_bl = 255;
  if (duty_bl < 0) duty_bl = 0;
  int high_bl = SOFT_PWM_PERIOD * duty_bl / 255;
  int low_bl = SOFT_PWM_PERIOD - high_bl;
  if (soft_pwm_bl_forward) {
    digitalWrite(TRACK_BL_DIR1, HIGH); digitalWrite(TRACK_BL_DIR2, LOW);
  } else {
    digitalWrite(TRACK_BL_DIR1, LOW); digitalWrite(TRACK_BL_DIR2, HIGH);
  }
  if (duty_bl > 0) {
    if (!pwm_bl_state && (now - pwm_bl_start >= low_bl)) {
      digitalWrite(TRACK_BL_PWM, HIGH);
      pwm_bl_state = true;
      pwm_bl_start = now;
    }
    if (pwm_bl_state && (now - pwm_bl_start >= high_bl)) {
      digitalWrite(TRACK_BL_PWM, LOW);
      pwm_bl_state = false;
      pwm_bl_start = now;
    }
  } else {
    digitalWrite(TRACK_BL_PWM, LOW);
    pwm_bl_state = false;
    pwm_bl_start = now;
  }

  // 后右
  int duty_br = soft_pwm_br_speed;
  if (duty_br > 255) duty_br = 255;
  if (duty_br < 0) duty_br = 0;
  int high_br = SOFT_PWM_PERIOD * duty_br / 255;
  int low_br = SOFT_PWM_PERIOD - high_br;
  if (soft_pwm_br_forward) {
    digitalWrite(TRACK_BR_DIR1, HIGH); digitalWrite(TRACK_BR_DIR2, LOW);
  } else {
    digitalWrite(TRACK_BR_DIR1, LOW); digitalWrite(TRACK_BR_DIR2, HIGH);
  }
  if (duty_br > 0) {
    if (!pwm_br_state && (now - pwm_br_start >= low_br)) {
      digitalWrite(TRACK_BR_PWM, HIGH);
      pwm_br_state = true;
      pwm_br_start = now;
    }
    if (pwm_br_state && (now - pwm_br_start >= high_br)) {
      digitalWrite(TRACK_BR_PWM, LOW);
      pwm_br_state = false;
      pwm_br_start = now;
    }
  } else {
    digitalWrite(TRACK_BR_PWM, LOW);
    pwm_br_state = false;
    pwm_br_start = now;
  }

  delay(1);
}

// 命令处理函数
void processCommand(String cmd) {
  if (cmd.length() == 0) return;

  Serial2.print("CMD: '");
  Serial2.print(cmd);
  Serial2.println("'");

  if (cmd.length() < 2) {
    Serial2.print("命令太短: ");
    Serial2.println(cmd);
    return;
  }

  char type = cmd.charAt(0);
  char direction = cmd.charAt(1);

  if (type == 'W' || type == 'w') {
    // 支持WF,左,右格式
    if (direction == 'F' || direction == 'f') {
      int left = ESC_MAX;
      int right = ESC_MAX;
      int comma1 = cmd.indexOf(',');
      int comma2 = cmd.lastIndexOf(',');
      if (comma1 > 1 && comma2 > comma1) {
        left = cmd.substring(comma1 + 1, comma2).toInt();
        right = cmd.substring(comma2 + 1).toInt();
        // 限制范围
        if (left < ESC_STOP) left = ESC_STOP;
        if (left > ESC_MAX) left = ESC_MAX;
        if (right < ESC_STOP) right = ESC_STOP;
        if (right > ESC_MAX) right = ESC_MAX;
      }
      currentLeftThrust = left;
      currentRightThrust = right;
      thrusterActive = true;
      setThruster(currentLeftThrust, currentRightThrust);
      Serial2.print("推进器: 前进 左=");
      Serial2.print(left);
      Serial2.print(" 右=");
      Serial2.println(right);
      digitalWrite(LED_PIN, LOW);
      return;
    }
    switch (direction) {
      case 'L': case 'l':
        currentLeftThrust = ESC_STOP;
        currentRightThrust = ESC_MAX;
        thrusterActive = true;
        setThruster(currentLeftThrust, currentRightThrust);
        Serial2.println("推进器: 左转");
        digitalWrite(LED_PIN, LOW);
        break;
      case 'R': case 'r':
        currentLeftThrust = ESC_MAX;
        currentRightThrust = ESC_STOP;
        thrusterActive = true;
        setThruster(currentLeftThrust, currentRightThrust);
        Serial2.println("推进器: 右转");
        digitalWrite(LED_PIN, LOW);
        break;
      default:
        currentLeftThrust = ESC_STOP;
        currentRightThrust = ESC_STOP;
        thrusterActive = false;
        setThruster(currentLeftThrust, currentRightThrust);
        Serial2.println("推进器: 停止");
        digitalWrite(LED_PIN, HIGH);
        break;
    }
  } else if ((type == 'T' || type == 't') || (type == 'U' || type == 'u')) {
    int speed = (type == 'U' || type == 'u') ? TRACK_PWM_MAX : TRACK_PWM_TURN;
    switch (direction) {
      case 'F': case 'f':
        setTrackMotorSoftPWM(0, speed, true);
        setTrackMotorSoftPWM(1, speed, true);
        setTrackMotorSoftPWM(2, speed, true);
        setTrackMotorSoftPWM(3, speed, true);
        trackActive = true;
        digitalWrite(LED_PIN, LOW);
        Serial2.println((type == 'U' || type == 'u') ? "履带: 快速前进" : "履带: 前进");
        break;
      case 'B': case 'b':
        setTrackMotorSoftPWM(0, speed, false);
        setTrackMotorSoftPWM(1, speed, false);
        setTrackMotorSoftPWM(2, speed, false);
        setTrackMotorSoftPWM(3, speed, false);
        trackActive = true;
        digitalWrite(LED_PIN, LOW);
        Serial2.println((type == 'U' || type == 'u') ? "履带: 快速后退" : "履带: 后退");
        break;
      case 'L': case 'l':
        setTrackMotorSoftPWM(0, TRACK_PWM_TURN, true);
        setTrackMotorSoftPWM(1, speed, true);
        setTrackMotorSoftPWM(2, TRACK_PWM_TURN, true);
        setTrackMotorSoftPWM(3, speed, true);
        trackActive = true;
        digitalWrite(LED_PIN, LOW);
        Serial2.println((type == 'U' || type == 'u') ? "履带: 快速左转" : "履带: 左转");
        break;
      case 'R': case 'r':
        setTrackMotorSoftPWM(0, speed, true);
        setTrackMotorSoftPWM(1, TRACK_PWM_TURN, true);
        setTrackMotorSoftPWM(2, speed, true);
        setTrackMotorSoftPWM(3, TRACK_PWM_TURN, true);
        trackActive = true;
        digitalWrite(LED_PIN, LOW);
        Serial2.println((type == 'U' || type == 'u') ? "履带: 快速右转" : "履带: 右转");
        break;
      default:
        stopAllTracks();
        trackActive = false;
        digitalWrite(LED_PIN, HIGH);
        Serial2.println("履带: 停止");
        break;
    }
  }
  else {
    Serial2.print("未知命令: ");
    Serial2.println(cmd);
  }
}

// 推进器控制
void setThruster(int left, int right) {
  leftThruster.writeMicroseconds(left + LEFT_THRUSTER_OFFSET);
  rightThruster.writeMicroseconds(right + RIGHT_THRUSTER_OFFSET);
}

// 履带电机控制
void setTrackMotor(int pwmPin, int dir1Pin, int dir2Pin, int speed, bool forward) {
  if (forward) {
    digitalWrite(dir1Pin, HIGH);
    digitalWrite(dir2Pin, LOW);
  } else {
    digitalWrite(dir1Pin, LOW);
    digitalWrite(dir2Pin, HIGH);
  }
  analogWrite(pwmPin, speed);
}

// 停止所有履带
void stopAllTracks() {
  if (thrusterActive) {
    setThruster(currentLeftThrust, currentRightThrust);
  } else {
    setThruster(ESC_STOP, ESC_STOP);
  }

  soft_pwm_fl_speed = 0;
  soft_pwm_fr_speed = 0;
  soft_pwm_bl_speed = 0;
  soft_pwm_br_speed = 0;

  digitalWrite(TRACK_FL_DIR1, LOW);
  digitalWrite(TRACK_FL_DIR2, LOW);
  digitalWrite(TRACK_FR_DIR1, LOW);
  digitalWrite(TRACK_FR_DIR2, LOW);
  digitalWrite(TRACK_BL_DIR1, LOW);
  digitalWrite(TRACK_BL_DIR2, LOW);
  digitalWrite(TRACK_BR_DIR1, LOW);
  digitalWrite(TRACK_BR_DIR2, LOW);

  if (thrusterActive) {
    setThruster(currentLeftThrust, currentRightThrust);
  } else {
    setThruster(ESC_STOP, ESC_STOP);
  }
}

// 软件PWM履带控制
void setTrackMotorSoftPWM(int track_id, int speed, bool forward) {
  switch(track_id) {
    case 0:
      soft_pwm_fl_speed = speed;
      soft_pwm_fl_forward = forward;
      break;
    case 1:
      soft_pwm_fr_speed = speed;
      soft_pwm_fr_forward = forward;
      break;
    case 2:
      soft_pwm_bl_speed = speed;
      soft_pwm_bl_forward = forward;
      break;
    case 3:
      soft_pwm_br_speed = speed;
      soft_pwm_br_forward = forward;
      break;
  }
}

// LED闪烁
void ledBlink(int times, int delayMs) {
  Serial2.print("LED指示 ");
  Serial2.print(times);
  Serial2.println(" 次");

  for (int i = 0; i < times; i++) {
    digitalWrite(LED_PIN, LOW);

    unsigned long startTime = millis();
    while (millis() - startTime < delayMs) {
      if (thrusterActive) {
        setThruster(currentLeftThrust, currentRightThrust);
      } else {
        setThruster(ESC_STOP, ESC_STOP);
      }
      delay(1);
    }

    digitalWrite(LED_PIN, HIGH);

    startTime = millis();
    while (millis() - startTime < delayMs) {
      if (thrusterActive) {
        setThruster(currentLeftThrust, currentRightThrust);
      } else {
        setThruster(ESC_STOP, ESC_STOP);
      }
      delay(1);
    }
  }
}


