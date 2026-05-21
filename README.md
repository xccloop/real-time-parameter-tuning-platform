# Real-Time Parameter Tuning Platform
## 龙芯 LS2K0300 智能车 — epoll 实时参数在线调试系统

### 一句话描述

通过串口（UART1），在运行时实时查看和修改系统参数（如 PID 增益、目标速度），
**无需重新编译、无需重启程序、无需停止运行**。参数修改即刻生效，主循环每秒自动
打印当前值以供验证。

### 核心场景

```
电脑端 (screen /dev/ttyUSB0 115200)          板子端 (LS2K0300)
┌─────────────────────────────────┐     ┌──────────────────────────┐
│ +=============================+ │     │  while (1) {             │
│ | speed |  200 | Target speed  │ │     │    epoll_wait(100ms);   │
│ | kp    |   50 | PID P-gain    │ │     │    if (串口有输入)       │
│ | ki    |   10 | PID I-gain    │<──>│      shell.execute();   │
│ | kd    |   30 | PID D-gain    │ UART│                          │
│ +=============================+ │     │    if (1秒到了)          │
│                                 │     │      print_tuning();     │
│ kyl-epoll> set speed 500  ←───  │     │  }                       │
│ kyl-epoll>                    │     └──────────────────────────┘
│                                 │       ↑ 参数表每秒自动刷新
│ +=============================+ │       下一轮打印立刻显示 speed=500
│ | speed |  500 | Target speed  │ │
│ | kp    |   50 | PID P-gain    │ │
│ | ki    |   10 | PID I-gain    │ │
│ | kd    |   30 | PID D-gain    │ │
│ +=============================+ │
└─────────────────────────────────┘
```

### 技术栈

| 层 | 技术 | 说明 |
|---|------|------|
| I/O 复用 | Linux epoll (边沿触发 ET) | 零阻塞、零轮询、O(1) 事件分发 |
| 串口 | UART1 /dev/ttyS1 @ 115200 8N1 | 逐字符回显，VT100 退格 |
| Shell | 自研 tokenizer (~60行) | 空白分割，引号支持，零依赖 |
| 参数管理 | TuningPlatform (单例) | 注册-读写-越界检查 |
| 编译 | loongarch64-linux-gnu-g++ 11.4 | 龙芯交叉编译工具链 |
| 目标 | LS2K0300 (LoongArch) | 龙芯嵌入式 Linux |

### 快速上手

```bash
# 1. 编译
cd /home/lq/Desktop/EPOLL/_ls2k0300
./build.sh

# 2. 部署到板子
./build.sh 10.163.14.121 -r

# 3. 连接串口
screen /dev/ttyUSB0 115200

# 4. 看到参数表每秒自动刷新
# 5. 输入命令修改参数
kyl-epoll> set speed 500     # 修改目标速度
kyl-epoll> set kp 75         # 修改 P 增益
kyl-epoll> get               # 手动刷新参数表
kyl-epoll> help              # 查看所有命令
```

### 命令列表

| 命令 | 参数 | 说明 |
|------|------|------|
| `help` | — | 显示所有命令 |
| `status` | — | 系统资源状态（RAM、Load 等） |
| `echo` | `<text>` | 回显文本 |
| `uptime` | — | 系统运行时间 |
| `uname` | — | 内核版本和架构 |
| `reboot` | — | 重启系统（需 root） |
| `set` | `<name> <value>` | **设置可调参数** |
| `get` | — | 手动刷新参数表 |

### 可调参数

| 参数名 | 默认值 | 范围 | 说明 |
|--------|--------|------|------|
| `speed` | 200 | 0 ~ 1000 | 目标速度 (mm/s) |
| `kp` | 50 | 0 ~ 500 | PID 比例系数 (×0.01) |
| `ki` | 10 | 0 ~ 500 | PID 积分系数 (×0.01) |
| `kd` | 30 | 0 ~ 500 | PID 微分系数 (×0.01) |

### 项目结构

```
_ls2k0300/
├── main.cpp                     # 主循环（epoll 事件驱动 + 每秒打印参数表）
├── build.sh                     # 交叉编译与部署脚本
├── CMakeLists.txt               # CMake 构建配置
├── toolchain_path.cmake         # 工具链路径（自动生成，不提交 git）
├── include/
│   ├── epoll.hpp                # epoll C++ 封装类
│   ├── shell.hpp                # 命令行 Shell（命令注册 + 解析）
│   ├── commands.hpp             # 内置命令声明 + 全局参数 extern
│   ├── tuning_platform.hpp      # 实时参数管理平台
│   └── uart1.hpp                # UART1 驱动（初始化和 fd 获取）
├── src/
│   ├── epoll.cpp                # epoll 封装实现
│   ├── shell.cpp                # Shell 解析和执行实现
│   ├── commands.cpp             # 内置命令实现（help/status/set/get...）
│   ├── tuning_platform.cpp      # 参数注册/读写/列表
│   ├── uart1.cpp                # UART1 串口配置
│   └── Init.cpp / Vofa.cpp ...  # 原有模块（保留兼容）
├── doc/
│   ├── design.md                # 项目构思与架构设计
│   ├── epoll-principle.md       # epoll 内核原理深度解析
│   └── problems-and-solutions.md # 实际遇到的 7 个问题及解决
└── libraries/                   # 龙芯框架库（zf_common/zf_device/zf_driver）
```

### 设计思想

**传统开发痛点**：修改 PID 参数 → 改代码 → 交叉编译 (30s) → scp 传文件 → 重启程序
→ 观察效果 → 不行再改... 一轮至少 1 分钟。

**本平台方案**：串口输入 "set kp 75" → 立刻生效 → 下 1 秒看到参数表刷新 → 确认效果。
全程 < 3 秒。

这就是 "Real-Time Parameter Tuning" 的含义：
- **Real-Time**：修改即时生效，无需重启
- **Parameter**：PID 增益、目标速度、阈值等任意可调数值
- **Tuning**：在线调优，所见即所得
- **Platform**：注册式架构，添加新参数只需一行代码

### License

MIT
