# 项目构想与架构设计

## 一、项目起源

### 1.1 为什么要做这个项目

智能车开发中有个极其痛苦的循环：

```
改 PID 参数 → 改 C 代码 → 交叉编译 (30s) → scp 传文件到板子 → 重启程序
→ 跑一圈看效果 → 不行，再来一遍...
```

一轮迭代至少 1-2 分钟。而 PID 调参通常需要几十甚至上百轮——半天就没了。

**核心洞察**：嵌入式 Linux 板子本身就有完整的操作系统内核，为什么不能像配置服务器
那样，在运行时动态修改参数？

### 1.2 设计目标

| 目标 | 说明 | 实现方式 |
|------|------|----------|
| 实时交互 | 串口发命令，即刻得到响应 | epoll 事件驱动 + 非阻塞 I/O |
| 在线调参 | 修改变量值无需重新编译 | 全局变量 + 串口命令 setter |
| 可视化反馈 | 参数变化立刻可见 | 主循环每秒打印参数表 |
| 零空转 CPU | 不等数据时不占 CPU | epoll_wait 挂起，硬件中断唤醒 |
| 可扩展 | 新增参数只需一行代码 | 注册式 TuningPlatform |
| 轻量化 | 不依赖 readline/ncurses | 自研 60 行 tokenizer |

---

## 二、架构设计

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        LS2K0300 板子                            │
│                                                                 │
│  ┌──────────┐    ┌──────────────┐    ┌─────────────────────┐   │
│  │ 电脑终端   │    │   UART1 驱动  │    │    Epoll 事件循环    │   │
│  │ (screen)  │<-->│ /dev/ttyS1   │<-->│  epoll_wait(100ms)  │   │
│  └──────────┘    └──────────────┘    └────────┬────────────┘   │
│                                                │               │
│                          ┌─────────────────────┤               │
│                          │                     │               │
│                    ┌─────▼──────┐     ┌───────▼──────────┐    │
│                    │ Shell 命令  │     │  定时器（超时）    │    │
│                    │ 解析与执行   │     │  每秒触发         │    │
│                    └─────┬──────┘     └───────┬──────────┘    │
│                          │                     │               │
│                    ┌─────▼──────┐     ┌───────▼──────────┐    │
│                    │  命令处理器  │     │  打印参数表       │    │
│                    │ (cmd_set等) │     │  print_tuning()  │    │
│                    └─────┬──────┘     └──────────────────┘    │
│                          │                                     │
│                    ┌─────▼──────┐                              │
│                    │TuningPlatform│ ← 全局变量映射              │
│                    │ 参数读写引擎  │   g_param_speed/kp/ki/kd   │
│                    └────────────┘                              │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 数据流

```
时刻 T0: 主循环打印
  +=============+
  | speed | 200 |
  | kp    |  50 |
  | ki    |  10 |
  | kd    |  30 |
  +=============+

时刻 T0 + 0.3s: 用户输入 "set speed 500\r"
  → UART 硬件中断 → 内核 tty 驱动 → ep_poll_callback
  → epoll_wait 被唤醒返回 → 逐字符 read 到 EAGAIN
  → line_buf = "set speed 500"
  → Shell::execute() → cmd_set(argc=3, argv=["set","speed","500"])
  → TuningPlatform::set_param("speed", 500)
  → g_param_speed = 500  ←── 变量已修改！
  → printf("[tuning] 'speed' = 500")

时刻 T0 + 1.0s: 定时器到，打印参数表
  +=============+
  | speed | 500 |  ←── 已改变！
  | kp    |  50 |
  | ki    |  10 |
  | kd    |  30 |
  +=============+
```

### 2.3 模块说明

#### Epoll 封装 (epoll.hpp/cpp)

```
┌──────────────────────┐
│  class Epoll          │
│  ─────────────────── │
│  create(max_events)   │ → epoll_create1(EPOLL_CLOEXEC)
│  add(fd, events)      │ → epoll_ctl(EPOLL_CTL_ADD)
│  mod(fd, events)      │ → epoll_ctl(EPOLL_CTL_MOD)
│  del(fd)              │ → epoll_ctl(EPOLL_CTL_DEL)
│  wait(timeout_ms)     │ → epoll_wait
│  ready_fd(i)          │ → events[i].data.fd
│  ready_events(i)      │ → events[i].events
│  destroy()            │ → close(epfd)
└──────────────────────┘
```

- 默认边沿触发 (ET) 模式，减少 epoll_wait 唤醒次数
- UART fd 必须为非阻塞（已由 uart1_init 设置 O_NONBLOCK）
- 支持事件类型：EPOLLIN / EPOLLOUT / EPOLLERR / EPOLLHUP

#### Shell (shell.hpp/cpp)

```
┌──────────────────────┐
│  class Shell          │
│  ─────────────────── │
│  register_cmd(...)    │ → 向命令表添加 {name, help, handler}
│  execute(line)        │ → tokenize → 查表 → handler(argc, argv)
│  prompt()             │ → printf("kyl-epoll> ")
│  print_help()         │ → 遍历命令表打印帮助
└──────────────────────┘
```

- Tokenizer：空格和 Tab 分割，引号内保留空白
- 空行和纯空白行静默忽略
- 未识别的命令打印 "command not found"

#### TuningPlatform (tuning_platform.hpp/cpp)

```
┌──────────────────────────────┐
│  class TuningPlatform (单例)  │
│  ────────────────────────────│
│  instance()                   │ → 获取单例
│  register_param(name, ptr,    │ → 注册参数到管理表
│                 min, max,     │
│                 desc)         │
│  set_param(name, value)       │ → 更改参数值 + 越界检查
│  get_param(name, &value)      │ → 读取当前值
│  list_params()                │ → 格式化打印所有参数
└──────────────────────────────┘
```

- 单例模式，全局唯一实例
- 每个参数存储：name、min、max、desc，以及指向外部变量的指针
- set 时同时修改内部表和外部的实际变量
- 越界检查：超过 min/max 时拒绝修改并报错

#### 命令处理器 (commands.cpp)

| 命令 | 函数 | 功能 |
|------|------|------|
| `help` | cmd_help | 列出所有可用命令 |
| `status` | cmd_status | 系统信息（uptime/RAM/Load/进程数） |
| `echo` | cmd_echo | 回显文本 |
| `uptime` | cmd_uptime | 系统运行时间 |
| `uname` | cmd_uname | 内核版本和架构 |
| `reboot` | cmd_reboot | 重启系统 |
| `set` | cmd_set | **设置可调参数** |
| `get` | cmd_get | **手动刷新参数表** |

---

## 三、技术选型与权衡

### 3.1 为什么用 epoll 而不是 select/poll

| 维度 | select | poll | epoll (选用) |
|------|--------|------|-------------|
| 时间复杂度 | O(n) | O(n) | **O(1)** |
| fd 数量限制 | 1024 | 无限制但慢 | **无限制（内存约束）** |
| 内核-用户拷贝 | 每次全量 | 每次全量 | **只拷贝就绪的** |
| 触发模式 | LT only | LT only | **LT + ET** |
| 适用场景 | 少量 fd | 中量 fd | **大量 fd / 低延迟** |

虽然本项目只监听 1 个 fd（UART），但选择 epoll 是为了：
1. **架构前瞻性**——后续添加按键 GPIO、编码器、网络 Socket 等，一行 `ep.add()` 即可
2. **学习价值**——理解 epoll 是嵌入式 Linux 开发的必修课
3. **性能知识**——epoll 的 ET 模式是工程上的最佳实践

### 3.2 边沿触发 vs 水平触发

```
水平触发 LT (默认)        │  边沿触发 ET (本项目)
                         │
数据到达 → 通知           │  数据到达 → 通知
read 一半 → 仍通知        │  read 一半 → 不再通知
必须读完才不再通知        │  只通知一次状态变化
                         │
✅ 简单，不会丢事件       │  ✅ 性能更好（少唤醒）
✅ 适合阻塞 fd            │  ✅ 适合非阻塞 fd
❌ 未读空时会反复唤醒      │  ❌ 必须配合 while-read 到 EAGAIN
```

本项目选择 ET 的原因：
- UART fd 已设为 O_NONBLOCK
- 逐字符 `while (read) until EAGAIN` 已实现
- 减少无畏的 epoll_wait 唤醒

### 3.3 为什么自研 Shell 而不是用 readline

| 依赖 | 优点 | 缺点 |
|------|------|------|
| GNU readline | 功能全、历史、补全 | **交叉编译困难、需要 libncurses、体积大** |
| 自研 tokenizer | **零依赖、60行、完全可控** | 无历史记录和补全 |

对于嵌入式板子，零依赖 > 功能丰富。历史记录可由终端软件（screen/minicom）的
scrollback buffer 提供，不占用板子资源。

---

## 四、扩展指南

### 添加新的可调参数

```cpp
// 1. 在 main.cpp 中定义全局变量
int g_param_threshold = 100;

// 2. 在 init_tuning_platform() 中注册
tp.register_param("thresh", &g_param_threshold, 0, 500, "Threshold value");

// 3. 在 print_tuning_status() 中添加打印行
printf("| thresh | %7d | %9d | %9d |  Threshold value      |\n",
       g_param_threshold, 0, 500);
```

无需修改任何其他代码，`set thresh 200` 立刻可用。

### 添加新的 epoll 监听 fd

```cpp
// 1. 打开设备（以按键 GPIO 为例）
int key_fd = open("/dev/input/event0", O_RDONLY | O_NONBLOCK);

// 2. 注册到 epoll
ep.add(key_fd, EPOLLIN);

// 3. 在事件循环中添加处理分支
if (fd == key_fd && (ev & EPOLLIN)) {
    struct input_event evt;
    read(key_fd, &evt, sizeof(evt));
    // 处理按键事件
}
```

### 添加自定义命令

```cpp
// 1. 实现处理函数
static void cmd_mycommand(int argc, char **argv) {
    printf("My command executed with %d args\n", argc);
}

// 2. 注册
shell.register_cmd("mycmd", "My custom command", cmd_mycommand);
```

---

## 五、设计哲学

1. **简单即强大**：80% 的场景只需要看/改参数，不需要花哨功能
2. **零依赖优于功能全**：嵌入式环境资源有限，能不要的绝对不要
3. **注册优于硬编码**：新增参数/命令/设备只需注册，不改核心代码
4. **看清优于猜对**：参数表每秒刷新，状态透明，不用猜系统在干什么
5. **先跑通再优化**：第一版只关注能用，性能问题等跑起来再测

这就是 Real-Time Parameter Tuning Platform 的设计思想和实现方式。
