#!/bin/bash

# ================= 配置区域 =================
# 你提供的路径
PWM_PATH="/sys/devices/platform/pwm-fan/hwmon/hwmon4/pwm1"
RPM_PATH="/sys/class/hwmon/hwmon0/rpm"
# ===========================================

# 1. 检查是否为 Root 用户
if [ "$EUID" -ne 0 ]; then
  echo "错误: 请使用 root 运行此脚本！"
  echo "用法: 先进行 sudo su "
  exit 1
fi

# 2. 定义退出时的清理函数 (安全机制)
# 无论脚本是正常跑完，还是被你用 Ctrl+C 强行打断，都会执行这里
cleanup() {
    echo ""
    echo "----------------------------------------"
    echo "脚本即将退出..."
    echo "正在恢复 nvfancontrol 自动温控服务..."
    systemctl start nvfancontrol
    echo "恢复完成，安全退出。"
}

# 注册信号捕获：当脚本接收到 EXIT(退出), SIGINT(Ctrl+C), SIGTERM(终止) 信号时执行 cleanup
trap cleanup EXIT INT TERM

# 3. 停止自动温控服务
echo "正在停止 nvfancontrol 服务以获取控制权..."
systemctl stop nvfancontrol
sleep 1
echo "服务已停止，开始测试..."
echo "----------------------------------------"
echo "目标 PWM | 持续时间 | 当前转速 (RPM)"

# 4. 循环逻辑：PWM 从 0 到 250，每次增加 50
for pwm_val in {0..250..50}; do
    
    # 写入 PWM 值
    echo "$pwm_val" > "$PWM_PATH"
    
    # 内部循环：持续 5 秒，每秒读取一次转速
    for ((i=1; i<=5; i++)); do
        # 读取当前转速 (如果不转显示 0)
        if [ -f "$RPM_PATH" ]; then
            current_rpm=$(cat "$RPM_PATH")
        else
            current_rpm="Error"
        fi
        
        # 打印状态
        # 使用 printf 对齐格式：PWM占4位，时间占3位，RPM占5位
        printf "PWM: %-4s | %-2ss   | RPM: %s\n" "$pwm_val" "$i" "$current_rpm"
        
        # 等待 1 秒
        sleep 1
    done
    echo "----------------------------------------"
done

# 循环结束后，cleanup 函数会自动被触发