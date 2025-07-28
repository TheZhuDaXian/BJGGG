#include <Arduino.h>
#include <Servo.h>

// 舵机引脚定义
const int PAN_PIN = 9;    // 270°舵机 (水平)
const int TILT_PIN = 10;  // 180°舵机 (垂直)
const int TRIGGER_PIN = 8; // 触发信号引脚
const int LED_PIN = 13;   // 状态LED指示灯
const int LASER_PIN = 52; // EL01激光头引脚

Servo panServo;
Servo tiltServo;

// 初始位置
int panAngle = 135;   // 270°舵机中点 (270度舵机的中点)
int tiltAngle = 90;   // 180°舵机中点
bool triggerActive = false; // 触发状态
bool systemReady = false;   // 系统就绪状态

// 通信状态
unsigned long lastReceiveTime = 0;
const unsigned long TIMEOUT_MS = 2000;  // 2秒超时
bool communicationActive = false;

// 激光头控制
bool laserActive = false;
unsigned long laserStartTime = 0;
const unsigned long LASER_DURATION = 2000;  // 激光持续时间2秒
int laserPower = 255;  // 激光功率 (0-255, 255为最大功率)

// 平滑移动
int targetPanAngle = 135;
int targetTiltAngle = 90;
unsigned long lastMoveTime = 0;
const unsigned long MOVE_INTERVAL = 20;  // 20ms移动间隔，更平滑

// 函数声明
void smoothServoMovement();
void updateLEDStatus();
void controlLaser();

void setup() {
  Serial.begin(115200);  // 设置串口波特率
  
  // 初始化舵机
  panServo.attach(PAN_PIN);
  tiltServo.attach(TILT_PIN);
  
  // 初始化引脚
  pinMode(TRIGGER_PIN, OUTPUT);
  pinMode(LED_PIN, OUTPUT);
  pinMode(LASER_PIN, OUTPUT);  // 设置激光头引脚为输出
  
  // 初始化状态
  digitalWrite(TRIGGER_PIN, LOW);
  digitalWrite(LED_PIN, LOW);
  digitalWrite(LASER_PIN, LOW); // 激光头关闭，输出低电平（继电器默认不吸合）
  
  // 舵机归中
  panServo.write(panAngle);
  tiltServo.write(tiltAngle);
  
  // 启动指示 - LED闪烁3次
  for(int i = 0; i < 3; i++) {
    digitalWrite(LED_PIN, HIGH);
    delay(200);
    digitalWrite(LED_PIN, LOW);
    delay(200);
  }
  
  delay(1000);  // 等待舵机稳定
  systemReady = true;
  digitalWrite(LED_PIN, HIGH);  // 系统就绪，LED常亮
  
  Serial.println("BJG Camera Control System Ready!");
  Serial.println("Waiting for commands...");
}

void loop() {
  // 检查串口通信
  if (Serial.available() >= 5) {  // 接收5字节数据
    // 接收数据 (2字节水平 + 2字节垂直 + 1字节触发信号)
    byte panHigh = Serial.read();
    byte panLow = Serial.read();
    byte tiltHigh = Serial.read();
    byte tiltLow = Serial.read();
    byte trigger = Serial.read();  // 触发信号
    
    // 组合为16位整数
    int newPanAngle = (panHigh << 8) | panLow;
    int newTiltAngle = (tiltHigh << 8) | tiltLow;
    
    // 调试信息
    Serial.print("Received: P=");
    Serial.print(newPanAngle);
    Serial.print(", T=");
    Serial.print(newTiltAngle);
    Serial.print(", Trigger=");
    Serial.println(trigger);
    
    // 限制角度范围
    newPanAngle = constrain(newPanAngle, 0, 270);
    newTiltAngle = constrain(newTiltAngle, 0, 180);
    
    // 更新目标角度（用于平滑移动）
    targetPanAngle = newPanAngle;
    targetTiltAngle = newTiltAngle;
    
    // 更新通信状态
    lastReceiveTime = millis();
    if (!communicationActive) {
      communicationActive = true;
      Serial.println("Communication established!");
    }
    
    // 控制触发信号和激光
    if (trigger == 1 && !triggerActive) {
      digitalWrite(TRIGGER_PIN, HIGH);
      triggerActive = true;
      Serial.println("TRIGGER ACTIVATED!");
    } else if (trigger == 0 && triggerActive) {
      digitalWrite(TRIGGER_PIN, LOW);
      triggerActive = false;
      Serial.println("Trigger deactivated");
    }
    
    // 激光手动触发（trigger值为2时）
    if (trigger == 2 && !laserActive) {
      laserActive = true;
      laserStartTime = millis();
      digitalWrite(LASER_PIN, HIGH);
      Serial.println("Manual Laser FIRE! (2 seconds)");
    }
  }
  
  // 检查通信超时 - 仅用于状态指示，不自动归中
  if (communicationActive && (millis() - lastReceiveTime > TIMEOUT_MS)) {
    communicationActive = false;
    // 移除自动归中功能，保持当前位置
    Serial.println("Communication timeout - maintaining current position");
  }
  
  // 平滑移动舵机
  smoothServoMovement();
  
  // 激光头控制
  controlLaser();
  
  // LED状态指示
  updateLEDStatus();
}

// 平滑舵机移动函数
void smoothServoMovement() {
  if (millis() - lastMoveTime >= MOVE_INTERVAL) {
    bool moved = false;
    
    // 平滑移动水平舵机
    if (panAngle != targetPanAngle) {
      int diff = targetPanAngle - panAngle;
      if (abs(diff) <= 1) {
        panAngle = targetPanAngle;
      } else {
        panAngle += (diff > 0) ? 1 : -1;
      }
      panServo.write(panAngle);
      moved = true;
    }
    
    // 平滑移动垂直舵机
    if (tiltAngle != targetTiltAngle) {
      int diff = targetTiltAngle - tiltAngle;
      if (abs(diff) <= 1) {
        tiltAngle = targetTiltAngle;
      } else {
        tiltAngle += (diff > 0) ? 1 : -1;
      }
      tiltServo.write(tiltAngle);
      moved = true;
    }
    
    lastMoveTime = millis();
  }
}

// LED状态指示函数
void updateLEDStatus() {
  static unsigned long ledBlinkTime = 0;
  static bool ledState = false;
  
  if (!systemReady) {
    // 系统未就绪，LED关闭
    digitalWrite(LED_PIN, LOW);
  } else if (laserActive) {
    // 激光头激活，LED超快闪（最高优先级）
    if (millis() - ledBlinkTime >= 100) {
      ledState = !ledState;
      digitalWrite(LED_PIN, ledState);
      ledBlinkTime = millis();
    }
  } else if (!communicationActive) {
    // 无通信，LED慢闪
    if (millis() - ledBlinkTime >= 1000) {
      ledState = !ledState;
      digitalWrite(LED_PIN, ledState);
      ledBlinkTime = millis();
    }
  } else if (triggerActive) {
    // 触发激活，LED快闪
    if (millis() - ledBlinkTime >= 200) {
      ledState = !ledState;
      digitalWrite(LED_PIN, ledState);
      ledBlinkTime = millis();
    }
  } else {
    // 正常工作，LED常亮
    digitalWrite(LED_PIN, HIGH);
  }
}

// 串口调试命令处理（已禁用，避免与二进制数据冲突）
/*
void handleSerialCommands() {
  if (Serial.available() > 0) {
    String command = Serial.readStringUntil('\n');
    command.trim();
    
    if (command == "STATUS") {
      Serial.print("System Status - Pan: ");
      Serial.print(panAngle);
      Serial.print("°, Tilt: ");
      Serial.print(tiltAngle);
      Serial.print("°, Trigger: ");
      Serial.print(triggerActive ? "ACTIVE" : "INACTIVE");
      Serial.print(", Comm: ");
      Serial.print(communicationActive ? "CONNECTED" : "DISCONNECTED");
      Serial.print(", Laser: ");
      Serial.println(laserActive ? "ON" : "OFF");
    }
    else if (command == "CENTER") {
      targetPanAngle = 135;
      targetTiltAngle = 90;
      Serial.println("Centering camera...");
    }
    else if (command == "RESET") {
      // 重置系统
      digitalWrite(TRIGGER_PIN, LOW);
      triggerActive = false;
      targetPanAngle = 135;
      targetTiltAngle = 90;
      Serial.println("System reset!");
    }
    else if (command == "on") {
      // 激活激光头继电器（高电平触发2秒）
      laserActive = true;
      laserStartTime = millis();
      digitalWrite(LASER_PIN, HIGH);
      Serial.println("Laser relay ON for 2 seconds");
    }
  }
}
*/

// 激光头控制函数
void controlLaser() {
  if (laserActive && (millis() - laserStartTime >= LASER_DURATION)) {
    laserActive = false;
    digitalWrite(LASER_PIN, LOW);  // 低电平关闭继电器
    Serial.println("Laser relay auto OFF after 2 seconds");
  }
}