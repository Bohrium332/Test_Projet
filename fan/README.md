# Jetson 风扇 PWM/RPM 测试脚本说明（README）

本脚本用于在 Jetson 设备上**临时接管风扇控制权**，按不同 PWM 值分档写入风扇控制节点，并在每个档位持续读取并打印转速（RPM），用于验证风扇 PWM 与转速的对应关系。

> ⚠️ 注意：不同 Jetson 型号/系统版本/载板，风扇控制节点与 RPM 节点路径可能不同。  
> 你需要先确认本机实际的 `pwm1` 和 `rpm` 路径，再运行脚本。

---

## 1. 脚本功能概览

- 尝试停止 `nvfancontrol` 服务（自动温控服务），以避免它覆盖你手动写入的 PWM。
- 将 PWM 从 `0` 到 `250`，每次步进 `50`：
  - 写入 PWM 值到 `PWM_PATH`
  - 每秒读取一次 `RPM_PATH`，持续 5 秒并打印
- 脚本退出时（包括 `Ctrl+C` 中断），会自动执行清理逻辑，**恢复启动 `nvfancontrol`**，避免长期失去温控保护。

---

## 2. 使用前的准备：确认 PWM / RPM 节点

### 2.1 确认 PWM 节点（pwm1 不一定在 hwmon4）

现在的是：

- `PWM_PATH="/sys/devices/platform/pwm-fan/hwmon/hwmon4/pwm1"`

但 `hwmon4` **不是固定编号**，可能重启后变化，也可能不同平台就是别的 `hwmonX`。

建议用以下方式确认哪个 hwmon 才是风扇控制（一般 name 会是 `pwmfan` / `pwm-fan` / 类似）：

```bash
for d in /sys/devices/platform/pwm-fan/hwmon/hwmon*; do
  echo "$d: $(cat $d/name 2>/dev/null)"
done
