# Real-Time Parameter Tuning Platform

龙芯 LS2K0300 智能车 **实时参数在线调优平台** — 板端 + 主机端完整方案。

```
板子 (LS2K0300 / LoongArch)              主机 (Windows / Linux)
┌─────────────────────────┐              ┌──────────────────────┐
│  epoll 事件驱动循环       │    UART串口   │  Python 串口监控仪表盘  │
│  ├─ 命令 Shell 解析      │<────────────>│  ├─ 实时参数可视化      │
│  ├─ 参数注册表            │   set speed   │  ├─ 曲线/进度条        │
│  ├─ 每秒打印参数表        │   get         │  ├─ 命令输入           │
│  └─ PID/编码器/PWM 控制   │              │  └─ 日志记录           │
└─────────────────────────┘              └──────────────────────┘
```

## 仓库结构

```
real-time-parameter-tuning-platform/
├── _ls2k0300/          # 板端：LoongArch 交叉编译 C++ 项目
│   ├── main.cpp        # 主循环（epoll 监听串口 + 参数表打印）
│   ├── include/        # 头文件（epoll, shell, tuning_platform 等）
│   ├── src/            # 源文件
│   ├── doc/            # 设计文档 / 原理分析 / 问题记录
│   └── build.sh        # 一键交叉编译
│
├── windows/            # 主机端：Python 串口监控仪表盘
│   ├── monitor.py      # Rich TUI 仪表盘（参数进度条 + 实时日志）
│   ├── install.bat     # Windows 一键安装
│   └── requirements.txt
│
└── README.md           # 你在这里
```

## 快速开始

### 1. 编译板端固件

```bash
cd _ls2k0300
bash build.sh
# 产出: build/main (loongarch64 ELF)
# SCP 到板子: scp build/main user@10.163.14.121:/root/
```

### 2. 运行主机监控

```bash
cd windows
pip install pyserial rich   # 或双击 install.bat
python monitor.py COM3      # 替换为实际串口号
```

### 3. 在线调参

在主机监控器中输入：
```
set speed 500    # 实时修改目标速度
set kp 80        # 调整 PID P 参数
get              # 手动刷新参数表
```

板子每秒自动发送参数表，主机实时可视化。

## 核心模块

| 模块 | 位置 | 说明 |
|------|------|------|
| epoll 事件框架 | `_ls2k0300/include/epoll.hpp` | 非阻塞 I/O 多路复用 |
| 命令 Shell | `_ls2k0300/include/shell.hpp` | 动态注册/解析/执行 |
| 参数管理 | `_ls2k0300/include/tuning_platform.hpp` | 类型安全 + 越界检查 |
| 串口驱动 | `_ls2k0300/include/uart1.hpp` | UART1 fd 暴露给 epoll |
| 监控仪表盘 | `windows/monitor.py` | Rich TUI 实时刷新 |

## 文档

- [设计文档](_ls2k0300/doc/design.md) — 项目构想与架构
- [epoll 原理](_ls2k0300/doc/epoll-principle.md) — epoll 内核机制详解
- [问题与解决](_ls2k0300/doc/problems-and-solutions.md) — 开发中遇到的问题

## 技术栈

- **板端**: C++17, CMake, epoll, LoongArch 交叉编译 (loongson-gnu-toolchain-8.3)
- **主机端**: Python 3.7+, pyserial, Rich TUI
- **通信**: UART 串口 (115200 8N1)
