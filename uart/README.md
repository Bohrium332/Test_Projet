# UART 波特率自动测试工具

## 项目简介

这是一套用于测试串口（UART/RS485/422/232）通信质量和寻找最佳波特率的Python工具。通过主从设备协同工作，自动测试多个波特率下的通信质量，并给出丢包率统计和最佳波特率推荐。

## 功能特性

- ✅ **自动握手协议**：主从设备自动扫描并建立连接
- ✅ **动态波特率切换**：运行时无需重启即可切换波特率
- ✅ **CRC16 校验**：采用 CRC16-CCITT 算法保证数据完整性
- ✅ **实时统计**：丢包率、错误帧、重复帧实时监控
- ✅ **批量测试**：支持多波特率顺序测试，自动筛选最佳配置
- ✅ **灵活配置**：可自定义测试包数量、负载大小、丢包阈值等参数

## 系统架构

```
┌─────────────────┐                    ┌─────────────────┐
│  uart_master.py │ ←─── UART/RS485───→│  uart_slave.py  │
│   (主控端)       │                    │   (设备端)       │
└─────────────────┘                    └─────────────────┘
     PC/工控机                                Jetson端
```

## 安装依赖

```bash
pip install pyserial
```

或使用 requirements.txt：

```bash
pip install -r requirements.txt
```

## 使用方法

### 1. 启动从设备（Slave）

在目标测试设备上运行：

```bash
python3 uart_slave.py --port /dev/ttyTHS0 --baud-list 115200,230400,460800,921600,1500000,2000000
```

**参数说明：**
- `--port`: 串口设备路径（默认 `/dev/ttyTHS0`）
- `--baud-list`: 扫描的波特率列表，逗号分隔（默认包含8个常用波特率）
- `--scan-dwell-ms`: 每个波特率扫描停留时间，单位毫秒（默认 200ms）
- `--idle-timeout`: 无数据超时时间，超时后重新扫描（默认 3.0秒）

### 2. 启动主设备（Master）

在PC或主控端运行：

```bash
python3 uart_master.py --port /dev/ttyACM0 --baud-list 1500000,2000000 --num-packets 500
```

**参数说明：**
- `--port`: 串口设备路径（默认 `/dev/ttyACM0`）
- `--baud-list`: 要测试的波特率列表，逗号分隔（默认 `1500000,2000000`）
- `--payload-bytes`: 每个数据帧的负载大小（默认 240 字节）
- `--num-packets`: 每个波特率测试发送的包数量（默认 500）
- `--test-seconds`: 每个波特率测试时长（使用 num-packets 时此参数无效）
- `--loss-threshold`: 可接受的最大丢包率百分比（默认 0.1%）

## 统计指标说明

- **TX_frames**: Master 发送的帧总数
- **RX_ok**: Slave 成功接收的正确帧数
- **miss**: 序列号不连续导致的丢失帧数
- **bad**: CRC 校验失败的错误帧数
- **dup**: 重复接收的帧数（序列号小于期望值）
- **loss_rate**: 丢包率 = (miss + bad) / (ok + miss + bad) × 100%

## 故障排查

### 1. 握手失败 `[FATAL] handshake failed`

**可能原因：**
- 串口设备路径不正确
- TX/RX 线路未正确连接
- GND 未共地
- RS485 方向控制引脚配置错误
- 波特率列表不匹配（Master 和 Slave 的 baud-list 没有交集）

**解决方法：**
- 检查物理连接和接线
- 确认设备路径：`ls /dev/tty*`
- 使用万用表测试 TX/RX 电压
- 确保 Master 和 Slave 的 baud-list 有公共波特率

### 2. 切换波特率失败 `switch to XXX FAILED`

**可能原因：**
- 目标波特率硬件不支持
- 波特率切换时序不稳定
- 缓冲区数据未清空

**解决方法：**
- 减少测试的波特率范围，只测试硬件明确支持的值
- 增加 `set_baud_both()` 中的延时
- 检查串口驱动是否支持目标波特率

### 3. 高波特率丢包严重

**可能原因：**
- 线材质量差或过长
- 缺少终端电阻（RS485）
- CPU 负载过高，处理不及时
- 波特率超出硬件稳定工作范围

### 4. Slave 频繁超时重新扫描

**可能原因：**
- Master 测试间隔过长
- `--idle-timeout` 设置过短
- 数据传输中断

**解决方法：**
- 增加 `--idle-timeout` 值（如 5.0 或 10.0）
- 检查 Master 和 Slave 是否正常运行

## 高级用法

### 自定义大负载测试

```bash
# Master 端使用 1KB 负载，发送 1000 个包
python3 uart_master.py --payload-bytes 1024 --num-packets 1000 --baud-list 921600,1500000
```

### 严格丢包率阈值

```bash
# 只接受 0.01% 以下丢包率的波特率
python3 uart_master.py --loss-threshold 0.01 --baud-list 115200,230400,460800
```

### 快速扫描模式

```bash
# Slave 快速扫描，每个波特率只停留 100ms
python3 uart_slave.py --scan-dwell-ms 100
```

## 许可证

本项目采用 MIT 许可证。

**最后更新日期：** 2026-01-07
