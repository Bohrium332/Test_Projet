#!/bin/bash

# GPIO 引脚设置
GPIO_PIN=106
GPIO1_PIN=43
TIMEOUT=0.5  # 设置超时时间为0.5秒

echo "nihao"
# 无限循环，每隔200ms翻转一次
while true
do
    # 使用 timeout 设置最大执行时间为 0.5 秒
    sudo timeout $TIMEOUT gpioset --mode=wait gpiochip0 $GPIO_PIN=0
    sudo timeout $TIMEOUT gpioset --mode=wait gpiochip0 $GPIO1_PIN=0
    echo "Set GPIO$GPIO_PIN to 12V"

    # 等待200ms
    sleep 0.2

    # 使用 timeout 设置最大执行时间为 0.5 秒
    sudo timeout $TIMEOUT gpioset --mode=wait gpiochip0 $GPIO_PIN=1
    sudo timeout $TIMEOUT gpioset --mode=wait gpiochip0 $GPIO1_PIN=1
    echo "Set GPIO$GPIO_PIN to 0V"

    # 等待200ms
    sleep 0.2
done