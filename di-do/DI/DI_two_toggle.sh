#!/bin/bash

# GPIO 引脚设置
DI1_PIN=105
DI2_PIN=144

# 无限循环，每隔1秒检测一次DI口电平
while true
do
    # 读取 DI1 和 DI2 的电平状态
    DI1_STATE=$(sudo gpioget gpiochip0 $DI1_PIN)
    DI2_STATE=$(sudo gpioget gpiochip0 $DI2_PIN)

    # 输出调试信息
    echo "Reading DI1 ($DI1_PIN): $DI1_STATE"
    echo "Reading DI2 ($DI2_PIN): $DI2_STATE"

    # 判断电平状态并输出相应信息
    if [ $DI1_STATE -eq 0 ]; then
        echo "DI1 ($DI1_PIN) has 12V input."
    else
        echo "DI1 ($DI1_PIN) has no input voltage."
    fi
    sleep 0.5
    if [ $DI2_STATE -eq 0 ]; then
        echo "DI2 ($DI2_PIN) has 12V input."
    else
        echo "DI2 ($DI2_PIN) has no input voltage."
    fi

    # 等待1秒
    sleep 1
done
