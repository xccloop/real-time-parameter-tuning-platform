/**
 * Real-Time Parameter Tuning Platform
 * 龙芯 LS2K0300 智能车 — epoll 串口实时参数在线调试系统
 *
 * 核心演示：
 *   主循环每 1 秒打印可调参数表
 *   用户在电脑端 via 串口发送 "set speed 500" 即刻修改
 *   打印输出立即反映新值 —— 真正的"实时在线调参"
 *
 * 架构：
 *   UART1 (/dev/ttyS1)  <-->  Epoll 事件循环  <-->  Shell 命令解析器
 *                                                <-->  TuningPlatform 参数管理
 *
 * 工作流：
 *   1. 初始化 UART1 (115200 8N1)
 *   2. 创建 epoll 实例，注册 UART1 fd (EPOLLIN)
 *   3. 注册 4 个可调参数 (speed/kp/ki/kd) 到 TuningPlatform
 *   4. 主循环：
 *      a) epoll_wait(100ms) 等待串口输入
 *      b) 有输入 → 逐字符组装命令行 → 回车执行（如 "set kp 75"）
 *      c) 每 10 个超时周期(~1s) → 打印参数表
 *      d) 用户修改的值在下次打印中立即体现
 */

#include "zf_common_headfile.h"
#include "uart1.hpp"
#include "epoll.hpp"
#include "shell.hpp"
#include "commands.hpp"
#include "tuning_platform.hpp"

#include <cstdio>
#include <cstring>
#include <unistd.h>
#include <errno.h>

#define INPUT_BUF_SIZE    256     // 命令行最大长度
#define EPOLL_TIMEOUT_MS  100     // epoll_wait 超时（ms）
#define PRINT_INTERVAL    10      // 每 N 个超时周期打印一次参数表（10*100ms=1s）

// ============================================================================
// 全局可调参数 —— 这就是"可实时修改的变量"
// ============================================================================
int g_param_speed = 200;   // 目标速度 (mm/s),        范围: 0 ~ 1000
int g_param_kp    = 50;    // PID 比例系数 (x0.01),   范围: 0 ~ 500
int g_param_ki    = 10;    // PID 积分系数 (x0.01),   范围: 0 ~ 500
int g_param_kd    = 30;    // PID 微分系数 (x0.01),   范围: 0 ~ 500

// ============================================================================
// 辅助函数: 打印参数状态表（周期性调用）
// ============================================================================
static void print_tuning_status(int seconds)
{
    printf("\n");
    printf("+==================================================================+\n");
    printf("|    Real-Time Parameter Tuning Platform  |  Uptime: %3d s         |\n",
           seconds);
    printf("+--------+---------+-----------+-----------+-----------------------+\n");
    printf("| Param  |  Value  |    Min    |    Max    |  Description          |\n");
    printf("+--------+---------+-----------+-----------+-----------------------+\n");
    printf("| speed  | %7d | %9d | %9d |  Target speed (mm/s)  |\n",
           g_param_speed, 0, 1000);
    printf("| kp     | %7d | %9d | %9d |  PID P-gain (x0.01)   |\n",
           g_param_kp, 0, 500);
    printf("| ki     | %7d | %9d | %9d |  PID I-gain (x0.01)   |\n",
           g_param_ki, 0, 500);
    printf("| kd     | %7d | %9d | %9d |  PID D-gain (x0.01)   |\n",
           g_param_kd, 0, 500);
    printf("+--------+---------+-----------+-----------+-----------------------+\n");
    printf("|  Send 'set <name> <value>' to modify.  'get' to refresh.        |\n");
    printf("|  Example:  set speed 500                                        |\n");
    printf("+--------+---------+-----------+-----------+-----------------------+\n");
    printf("\n");
}

// ============================================================================
// 注册可调参数到 TuningPlatform
// ============================================================================
static void init_tuning_platform()
{
    TuningPlatform &tp = TuningPlatform::instance();

    tp.register_param("speed", &g_param_speed, 0,   1000, "Target speed (mm/s)");
    tp.register_param("kp",    &g_param_kp,    0,   500,  "PID P-gain (x0.01)");
    tp.register_param("ki",    &g_param_ki,    0,   500,  "PID I-gain (x0.01)");
    tp.register_param("kd",    &g_param_kd,    0,   500,  "PID D-gain (x0.01)");
}

// ============================================================================
// 主函数
// ============================================================================
int main()
{
    printf("\n");
    printf("==========================================================\n");
    printf("  Real-Time Parameter Tuning Platform\n");
    printf("  Board:  LS2K0300 (loongarch64)\n");
    printf("  UART1:  /dev/ttyS1 @ 115200 8N1\n");
    printf("  Build:  %s %s\n", __DATE__, __TIME__);
    printf("==========================================================\n");
    printf("\n");
    printf("  HOW TO USE:\n");
    printf("    1. Connect:  screen /dev/ttyUSB0 115200\n");
    printf("    2. Watch:    parameters auto-print every ~1 second\n");
    printf("    3. Tune:     type 'set speed 500' to change on-the-fly\n");
    printf("    4. Verify:   watch the printed value change\n");
    printf("\n");

    // ---- 1. 初始化 UART1 ----
    if (uart1_init() != 0)
    {
        fprintf(stderr, "FATAL: uart1_init failed, exiting\n");
        return 1;
    }
    int uart_fd = uart1_get_fd();

    // ---- 2. 创建 epoll 实例 ----
    Epoll ep;
    if (!ep.create(8))
    {
        fprintf(stderr, "FATAL: epoll create failed, exiting\n");
        uart1_close();
        return 1;
    }

    // ---- 3. 注册 UART1 fd ----
    if (!ep.add(uart_fd, EPOLLIN))
    {
        fprintf(stderr, "FATAL: epoll add uart1 failed, exiting\n");
        uart1_close();
        return 1;
    }

    // ---- 4. 初始化参数调优平台 ----
    init_tuning_platform();

    // ---- 5. 初始化命令 Shell ----
    Shell shell(32);
    register_builtin_commands(shell);

    // ---- 6. 行缓冲 ----
    char line_buf[INPUT_BUF_SIZE];
    int  line_pos = 0;
    memset(line_buf, 0, sizeof(line_buf));

    printf("\n");  // 额外空行，让第一个计时打印不被提示符干扰

    // ---- 7. 事件循环 ----
    int loop_count = 0;
    int print_tick = 0;

    while (1)
    {
        int nfds = ep.wait(EPOLL_TIMEOUT_MS);
        print_tick++;

        // --- 处理就绪事件（串口输入）---
        for (int i = 0; i < nfds; i++)
        {
            int fd = ep.ready_fd(i);
            uint32_t ev = ep.ready_events(i);

            // UART1 有数据可读
            if (fd == uart_fd && (ev & EPOLLIN))
            {
                char c;
                while (1)
                {
                    ssize_t n = read(uart_fd, &c, 1);
                    if (n <= 0)
                    {
                        if (n < 0 && errno == EAGAIN) break;
                        break;
                    }

                    // 字符回显
                    if (c != '\r' && c != '\n')
                    {
                        write(uart_fd, &c, 1);
                    }
                    else if (c == '\r')
                    {
                        write(uart_fd, "\r\n", 2);
                    }

                    // 回车 → 执行命令
                    if (c == '\r' || c == '\n')
                    {
                        line_buf[line_pos] = '\0';
                        if (line_pos > 0)
                        {
                            shell.execute(line_buf);
                        }
                        line_pos = 0;
                        memset(line_buf, 0, sizeof(line_buf));
                        shell.prompt();
                    }
                    // 退格
                    else if (c == 0x7F || c == '\b')
                    {
                        if (line_pos > 0)
                        {
                            line_pos--;
                            line_buf[line_pos] = '\0';
                            write(uart_fd, "\b \b", 3);
                        }
                    }
                    // 普通可打印字符
                    else if (c >= 0x20 && c <= 0x7E)
                    {
                        if (line_pos < INPUT_BUF_SIZE - 1)
                        {
                            line_buf[line_pos++] = c;
                        }
                    }
                }
            }

            // 异常事件
            if (ev & (EPOLLERR | EPOLLHUP))
            {
                fprintf(stderr, "epoll: fd=%d error/hangup (events=0x%x)\n", fd, ev);
                if (fd == uart_fd)
                {
                    ep.del(uart_fd);
                    uart1_close();
                    sleep(1);
                    if (uart1_init() == 0)
                    {
                        uart_fd = uart1_get_fd();
                        ep.add(uart_fd, EPOLLIN);
                        printf("UART1 reconnected\n");
                        shell.prompt();
                    }
                }
            }
        }

        // --- 周期性打印参数表（每秒一次）---
        if (print_tick >= PRINT_INTERVAL)
        {
            print_tick = 0;
            loop_count++;
            print_tuning_status(loop_count);
        }
    }

    // 清理（理论上不会到这里）
    ep.destroy();
    uart1_close();
    return 0;
}
