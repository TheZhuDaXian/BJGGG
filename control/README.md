# 综合控制中心命令大全

## 推进器相关
- WF,left,right  
  推进器前进，左/右速度（1050~2000），如：`WF,1500,1600`
- WL  
  推进器左转
- WR  
  推进器右转
- WS  
  推进器停止

## 履带相关
- TF  
  履带前进（低速）
- TB  
  履带后退（低速）
- TL  
  履带左转（低速）
- TR  
  履带右转（低速）
- TS  
  履带停止（低速）

- UF  
  履带前进（高速）
- UB  
  履带后退（高速）
- UL  
  履带左转（高速）
- UR  
  履带右转（高速）
- US  
  履带停止（高速）

## 其他
- RESET  
  软件复位
- 紧急停止  
  TS + WS

## 虚拟环境与依赖
1. 创建虚拟环境  
   `python -m venv venv`
2. 激活虚拟环境  
   Windows：`venv\Scripts\activate`  
   Linux/macOS：`source venv/bin/activate`
3. 安装依赖  
   `pip install -r requirements.txt`

## 重启nomachine
   /usr/NX/bin/nxserver --restart