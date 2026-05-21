# Windows 主机端监控程序

Real-Time Parameter Tuning Platform 的 Windows/Linux 主机端串口监控仪表盘。

## 功能

- 串口连接 LS2K0300 板子
- 实时解析板子每秒发送的参数表
- 可视化仪表盘（参数值 + 进度条 + 实时日志）
- 命令行交互：发送 `set speed 500` / `get` 等命令
- 自动重连

## 安装

### Windows

```batch
# 双击运行 install.bat
# 或手动：
pip install pyserial rich
```

### Linux

```bash
pip install pyserial rich
```

## 使用

```bash
# 列出可用串口
python monitor.py -l

# 连接板子
python monitor.py COM3          # Windows（根据实际串口号调整）
python monitor.py /dev/ttyUSB0  # Linux

# 指定波特率
python monitor.py COM3 -b 115200

# 简化模式（无需 Rich 库）
python monitor.py COM3 --simple
```

## 界面截图

```
┌──────────────────────────────────────────────────────┐
│  Real-Time Parameter Tuning Platform  —  Monitor     │
│  Port: COM3  Baud: 115200  Status: ● CONNECTED       │
├──────────────────────┬───────────────────────────────┤
│  PARAMETER DASHBOARD │  SERIAL LOG                   │
│                      │                               │
│  speed  ████████░░░   │  [10:30:15] +=============+  │
│        200 (0-1000)  │  [10:30:15] | speed | 200 |  │
│                      │  [10:30:16] | kp    |  50 |  │
│  kp     ██░░░░░░░░   │  [10:30:18] >>> SENT: set..  │
│        50 (0-500)    │  [10:30:18] [tuning] speed=  │
│                      │                               │
│  ki     ░░░░░░░░░░   │                               │
│        10 (0-500)    │                               │
│                      │                               │
│  kd     ███░░░░░░░   │                               │
│        30 (0-500)    │                               │
├──────────────────────┴───────────────────────────────┤
│  > set speed 500                                    │
└──────────────────────────────────────────────────────┘
```

## 快捷键

| 按键 | 功能 |
|------|------|
| Enter | 发送命令 |
| Backspace | 删除字符 |
| Ctrl+C | 退出程序 |
| `/quit` | 退出程序 |

## 工作原理

```
板子 (LS2K0300)                      主机 (Windows/Linux)
┌───────────────────┐               ┌─────────────────────┐
│ while(1) {        │    UART串口    │ SerialReader 线程   │
│   epoll_wait()    │──────────────>│   逐行读取           │
│   处理串口命令      │               │   解析参数表          │
│   每秒打印参数表    │               │   更新 AppState      │
│ }                 │               │                     │
│                   │  <────────────│ Keyboard 线程        │
│                   │   发送命令     │   用户输入 set/get    │
└───────────────────┘               └─────────────────────┘
                                           │
                                    Rich Live 渲染
                                    实时刷新 TUI 仪表盘
```
