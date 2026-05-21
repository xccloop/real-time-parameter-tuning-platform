# 实际问题与解决方案

本文档记录 Real-Time Parameter Tuning Platform 项目开发全过程中遇到的实际问题、
排查过程和最终解决方案。每个问题都是踩过的真实坑，供后续参考。

## 目录

1. [项目迁移后 CMake 路径失效](#1-项目迁移后-cmake-路径失效)
2. [GitHub 仓库命名与项目定位](#2-github-仓库命名与项目定位)
3. [EPOLLET 边沿触发丢数据](#3-epollet-边沿触发丢数据)
4. [串口回显卡顿与退格处理](#4-串口回显卡顿与退格处理)
5. [UART 断开重连](#5-uart-断开重连)
6. [交叉编译兼容性](#6-交叉编译兼容性)
7. [编码器破坏性读取（历史）](#7-编码器破坏性读取历史)
8. [参数越界检查](#8-参数越界检查)
9. [参数表打印与串口输入互相干扰](#9-参数表打印与串口输入互相干扰)

---

## 1. 项目迁移后 CMake 路径失效

### 问题

项目从 `/home/lq/Desktop/_ls2k0300/` 移动到 `/home/lq/Desktop/EPOLL/_ls2k0300/` 后，
编译失败：

```
CMake Error: toolchain not found at
  /home/lq/Desktop/_ls2k0300/tools/loongson-gnu-toolchain-8.3...
```

### 原因

`toolchain_path.cmake` 中硬编码了旧路径。该文件由 `build.sh` 第 604 行自动生成：

```bash
cat > "${TOOLCHAIN_CMAKE_MACRO_FILE}" << EOF
set(CMAKE_TOOLCHAIN_PATH "${toolchain_path}" CACHE PATH "..." FORCE)
EOF
```

其中 `toolchain_path` = `${TOOLS_DIR}/${TOOLCHAIN_DIR_NAME}`，`TOOLS_DIR` = `${SCRIPT_DIR}/tools`。

### 解决

1. 手动修正 `toolchain_path.cmake` 为新路径
2. `tools` 目录是符号链接 → `/home/lq/Desktop/car/tools`，工具链实际存在
3. 运行 `build.sh` 会自动重新生成正确的路径（但首次编译前需要修正）

### 预防

- 不在 CMakeLists.txt 中硬编码绝对路径，全部使用 `${CMAKE_SOURCE_DIR}` 和相对路径
- `build.sh` 已正确处理相对路径
- `.gitignore` 排除 `toolchain_path.cmake`，防止本地绝对路径污染远程仓库

---

## 2. GitHub 仓库命名与项目定位

### 问题

最初仓库命名为 `kyl-epoll`（"Kyl" + "epoll"），但这个名称有三个问题：

1. 没有体现项目的核心价值（Real-Time Parameter Tuning）
2. "epoll" 是实现细节，不是用户视角
3. 名称太技术化，不易理解项目用途

### 解决

通过 GitHub API `PATCH /repos/xccloop/kyl-epoll` 将仓库重命名为
`real-time-parameter-tuning-platform`，并同步更新：

- GitHub 远程 origin URL
- README.md 项目标题和说明
- doc/ 下的所有设计文档
- main.cpp 中的启动横幅

新名称 "Real-Time Parameter Tuning Platform" 准确描述了项目的核心价值：
在运行时实时调整参数，无需重启。

### 教训

- 仓库名应该从**用户价值**出发，而非从**技术实现**出发
- "这项目干什么用的" → 项目名应该直接回答这个问题
- 技术细节留给文档和代码注释

---

## 3. EPOLLET 边沿触发丢数据

### 问题

测试时发现：发送长命令 "echo hello world this is a very long message" 时，
Shell 只收到了 "echo hello" 就被截断了。

### 原因

epoll ET 模式只在**状态变化**时通知一次。如果一次 `read()` 没读完缓冲区的所有数据，
剩余数据不会触发新的 epoll_wait 返回。必须循环 read 直到返回 EAGAIN。

错误代码：
```c
// ❌ 只读一次，缓冲区剩余数据被"遗忘"
char buf[256];
int n = read(uart_fd, buf, sizeof(buf)-1);
```

### 解决

正确代码（本项目采用）：
```c
// ✅ 循环读到 EAGAIN 为止（逐字符版本）
while (1) {
    ssize_t n = read(uart_fd, &c, 1);
    if (n < 0) {
        if (errno == EAGAIN) break;  // 缓冲区已空
        break;
    }
    if (n == 0) break;
    // 处理字符 c
}
```

### 知识点

- ET 模式必须配合**非阻塞 fd**（O_NONBLOCK），否则 read 会阻塞
- 循环 read 是 ET 模式的强制要求，否则数据会丢失
- LT 模式无此问题，但会频繁唤醒 epoll_wait
- 逐字符 read 的好处：天然支持行编辑（退格、回显），不需要缓冲区管理

---

## 4. 串口回显卡顿与退格处理

### 问题

用户通过 `screen /dev/ttyUSB0 115200` 连接板子串口时，输入字符后回显有
明显延迟（> 100ms），体验很差。同时退格键行为因终端软件而异。

### 原因

最初实现中，数据到达后没有立即回显，而是等到整行处理完成才 printf 返回。
加上 epoll_wait 有 100ms 超时，导致用户感觉"输入没反应"。

退格键问题：
- `screen` 发送 `0x7F` (DEL)
- 某些终端发送 `0x08` (BS)
- 输入 `Ctrl+H` 也发送 `0x08`

### 解决

**逐字符即时回显**：
```c
// 字符到达即刻回显（逐字符 write 回 fd）
write(uart_fd, &c, 1);

// 回车时输出 \r\n
if (c == '\r') write(uart_fd, "\r\n", 2);

// 退格时输出 VT100 序列 \b \s \b
if (c == 0x7F) write(uart_fd, "\b \b", 3);
```

**VT100 退格序列解释**：
```
\b  → 光标左移一格
' ' → 用空格覆盖旧字符（视觉上"擦除"）
\b  → 光标再左移一格（回到原位）
```

这样用户看到的是字符被"擦除"，而屏幕缓冲区不会留下残影。

**兼容两种退格码**：
```c
else if (c == 0x7F || c == '\b')  // 同时处理 DEL 和 BS
```

---

## 5. UART 断开重连

### 问题

串口线意外拔出或 ttyUSB 断开后，程序检测到 fd 上出现 EPOLLERR/EPOLLHUP，
但之后无法自动恢复通信。

### 原因

- fd 上的错误事件不会自动消失
- close() 后 fd 失效，需要重新 open()
- 如果没有自动重连逻辑，只能手动重启程序

### 解决

在 epoll 事件循环中监控 `EPOLLERR | EPOLLHUP`：

```c
if (ev & (EPOLLERR | EPOLLHUP)) {
    if (fd == uart_fd) {
        ep.del(uart_fd);          // 从 epoll 移除
        uart1_close();            // 关闭 fd
        sleep(1);                 // 等待硬件稳定
        if (uart1_init() == 0) {  // 重新初始化（会重新 open /dev/ttyS1）
            uart_fd = uart1_get_fd();
            ep.add(uart_fd, EPOLLIN);
            printf("UART1 reconnected\n");
        }
    }
}
```

---

## 6. 交叉编译兼容性

### 问题

- `sys/sysinfo.h` 中 `struct sysinfo` 的字段名在 glibc 和 musl 之间可能不同
- LoongArch 工具链使用 glibc 2.28+，兼容主流字段名
- `sync()` + `system("reboot")` 需要 root 权限

### 解决

```c
// glibc 标准字段（LoongArch 工具链支持）
struct sysinfo si;
sysinfo(&si);
printf("RAM: %lu MB\n", (si.totalram * si.mem_unit) / (1024*1024));
printf("Uptime: %ld s\n", si.uptime);
```

### 验证

编译后在板子上运行，确认 `status` 和 `uptime` 命令输出正确数值。
LoongOS（板子精简 Linux）的 `/proc/meminfo` 与标准 Linux 一致。

---

## 7. 编码器破坏性读取（历史）

### 背景

`/dev/zf_encoder_quad_1` 和 `/dev/zf_encoder_quad_2` 的 `read()` 是破坏性读取——
每次 read 后内核计数器归零，只返回"自上次 read 以来的增量"。

### 影响

如果 ISR (每 10ms 调用 `Motor_Control()`) 和主循环同时读编码器，ISR 每 10ms
"吃掉"计数，导致主循环只能拿到 10ms 内的微小增量（-2 ~ 0），看起来像噪声。

### 排查过程

1. 怀疑编码器硬件故障 → 交换左右编码器插头测试 → 问题跟随移动
2. 用 `cat /proc/interrupts` 确认 GPIO 中断正常触发
3. 注释 ISR 中的 `Motor_Control()` → 编码器读数正常 → 确认为读取竞争问题

### 解决

- **epoll 系统中**：只在 epoll 事件循环中独占读取编码器，不在 ISR 中读取
- **生产代码中**：ISR 读取并累积，主循环通过共享变量获取，不直接 read 设备

### 教训

- 破坏性读取的设备必须单点访问
- 怀疑硬件前先排查软件竞争条件
- `/proc/interrupts` 是诊断 GPIO/编码器中断的金标准
- `encoder_clear_count()` 会永久禁用内核 GPIO 中断，只能 reboot 恢复

---

## 8. 参数越界检查

### 问题

用户通过串口输入 `set speed 5000`，但 speed 的有效范围是 [0, 1000]。
如果不做检查，可能导致后续代码出现未定义行为（如 PWM 占空比溢出、数组越界等）。

### 解决

在 `TuningPlatform::set_param()` 中强制越界检查：

```cpp
bool TuningPlatform::set_param(const char *name, int value)
{
    for (int i = 0; i < count_; i++)
    {
        if (strcmp(params_[i].name, name) == 0)
        {
            if (value < params_[i].min_val || value > params_[i].max_val)
            {
                printf("[tuning] ERROR: '%s' value %d out of range [%d, %d]\n",
                       name, value, params_[i].min_val, params_[i].max_val);
                return false;  // ← 拒绝修改，不生效
            }
            params_[i].value = value;
            *value_ptrs_[i] = value;   // 同步到外部变量
            printf("[tuning] '%s' = %d\n", name, value);
            return true;  // ← 修改成功
        }
    }
    printf("[tuning] ERROR: parameter '%s' not found\n", name);
    return false;
}
```

### 设计权衡

为什么不静默钳位（clamp 到 min/max）而是报错拒绝？

- **显式 > 隐式**：用户输入 `5000` 可能是手误，报错让他意识到问题
- **防止静默失败**：clamp 后用户看到 `1000` 以为设置成功，但实际不是他想要的值
- **调试友好**：报错消息告诉用户有效范围，方便快速纠正

---

## 9. 参数表打印与串口输入互相干扰

### 问题

参数表每秒打印一次（占约 12 行），如果此时用户正在输入命令，回显字符会
"嵌入"到参数表输出中，造成串口输出混乱。

例如：
```
+=============+
| kp    |  50 |set kp 80               ← 用户输入被参数表"吞"进去了
| ki    |  10 |
```

### 原因

参数表 printf 和用户回显 write 都输出到同一个 fd（/dev/ttyS1），
它们之间没有互斥机制。epoll_wait 的 100ms 超时返回时，可能同时处理
"打印参数表"和"回显字符"两个操作，输出交错。

### 解决（当前方案）

1. **不打印提示符**：移除了 `shell.prompt()` 的自动打印，参数表打印后
   不再有多余的 "kyl-epoll> " 干扰
2. **参数表最后一行提示**：在表格末尾打印 "Send 'set <name> <value>' to modify."
   作为交互引导
3. **用户输入不丢**：逐字符 read 保证每个字符都被处理，即使视觉上可能和
   参数表输出交错，但命令执行不会错

### 更完善的方案（TODO）

- 使用 ANSI 转义序列 `\033[2J\033[H` 清屏后重绘参数表
- 或者在打印前用 `\033[13A` 上移光标覆盖上一轮的参数表
- 但这会增加 VT100 依赖，与"零依赖"原则冲突

**当前方案的选择**：接受偶尔的视觉混乱，保证功能正确性。这在嵌入式调试场景
中是可以接受的——用户要么在观察参数，要么在输入命令，很少同时进行。

---

## 总结

这 9 个问题涵盖了嵌入式 Linux 开发中常见的几类挑战：

| 类别 | 问题 | 解决策略 |
|------|------|----------|
| 环境配置 | CMake 路径、工具链兼容 | 自动化脚本 + 相对路径 |
| I/O 模型 | EPOLLET 丢数据、回显卡顿 | 正确的 ET 用法 + 逐字符处理 |
| 健壮性 | UART 断开、参数越界 | 错误检测 + 自动恢复 + 边界检查 |
| 用户体验 | 退格键兼容、输出干扰 | VT100 控制码 + 权衡接受 |
| 项目定位 | 仓库命名、文档组织 | 用户价值导向 + 分层文档 |

每个问题都附带完整的排查过程和解决代码，方便后续维护和新人上手。
