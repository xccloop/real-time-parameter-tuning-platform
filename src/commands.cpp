#include "commands.hpp"
#include "tuning_platform.hpp"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <unistd.h>
#include <sys/sysinfo.h>
#include <sys/utsname.h>

// ============================================================================
// 内置命令实现
// ============================================================================

// ---- help ----------------------------------------------------------------
static void cmd_help(int argc, char **argv)
{
    (void)argc; (void)argv;
    printf("\nAvailable commands:\n");
    printf("  help       — Show this help\n");
    printf("  status     — System resource status (RAM, load...)\n");
    printf("  echo       — Echo text back, usage: echo <text>\n");
    printf("  uptime     — Show system uptime\n");
    printf("  uname      — Show kernel version and arch\n");
    printf("  reboot     — Reboot the system (needs root)\n");
    printf("  set        — Set a tuning parameter, usage: set <name> <value>\n");
    printf("  get        — Show all tuning parameters\n");
    printf("\n");
}

// ---- status --------------------------------------------------------------
static void cmd_status(int argc, char **argv)
{
    (void)argc; (void)argv;

    struct sysinfo si;
    if (sysinfo(&si) == 0)
    {
        long uptime_min = si.uptime / 60;
        printf("=== System Status ===\n");
        printf("  Uptime    : %ld min\n", uptime_min);
        printf("  Load      : %lu / %lu / %lu (1/5/15 min)\n",
               si.loads[0], si.loads[1], si.loads[2]);
        printf("  Total RAM : %lu MB\n", (si.totalram * si.mem_unit) / (1024*1024));
        printf("  Free RAM  : %lu MB\n", (si.freeram * si.mem_unit) / (1024*1024));
        printf("  Processes : %u\n", (unsigned)si.procs);
    }
    else
    {
        perror("sysinfo");
    }
}

// ---- echo ----------------------------------------------------------------
static void cmd_echo(int argc, char **argv)
{
    for (int i = 1; i < argc; i++)
    {
        if (i > 1) printf(" ");
        printf("%s", argv[i]);
    }
    printf("\n");
}

// ---- uptime --------------------------------------------------------------
static void cmd_uptime(int argc, char **argv)
{
    (void)argc; (void)argv;

    struct sysinfo si;
    if (sysinfo(&si) == 0)
    {
        long days  = si.uptime / 86400;
        long hours = (si.uptime % 86400) / 3600;
        long mins  = (si.uptime % 3600) / 60;
        printf("up %ld days, %ld:%02ld\n", days, hours, mins);
    }
}

// ---- uname ---------------------------------------------------------------
static void cmd_uname(int argc, char **argv)
{
    (void)argc; (void)argv;

    struct utsname buf;
    if (uname(&buf) == 0)
    {
        printf("%s %s %s %s %s\n",
               buf.sysname, buf.nodename, buf.release,
               buf.version, buf.machine);
    }
    else
    {
        perror("uname");
    }
}

// ---- reboot --------------------------------------------------------------
static void cmd_reboot(int argc, char **argv)
{
    (void)argc; (void)argv;

    printf("Rebooting in 1 second...\n");
    fflush(stdout);
    sync();
    if (system("reboot") != 0)
    {
        printf("reboot failed (need root?)\n");
    }
}

// ---- set（参数调优核心命令）----------------------------------------------
static void cmd_set(int argc, char **argv)
{
    if (argc < 3)
    {
        printf("Usage: set <name> <value>\n");
        printf("Example: set speed 500\n");
        printf("Use 'get' to see all parameters and their names.\n");
        return;
    }

    int value = atoi(argv[2]);
    TuningPlatform::instance().set_param(argv[1], value);
}

// ---- get（参数查看命令）--------------------------------------------------
static void cmd_get(int argc, char **argv)
{
    (void)argc; (void)argv;
    TuningPlatform::instance().list_params();
}

// ============================================================================
// 注册所有内置命令
// ============================================================================
void register_builtin_commands(Shell &shell)
{
    shell.register_cmd("help",   "Show available commands",               cmd_help);
    shell.register_cmd("status", "System resource status (RAM, load...)", cmd_status);
    shell.register_cmd("echo",   "Echo text back, usage: echo <text>",    cmd_echo);
    shell.register_cmd("uptime", "Show system uptime",                    cmd_uptime);
    shell.register_cmd("uname",  "Show kernel version and arch",          cmd_uname);
    shell.register_cmd("reboot", "Reboot the system (needs root)",        cmd_reboot);
    shell.register_cmd("set",    "Set a tuning parameter: set <name> <value>", cmd_set);
    shell.register_cmd("get",    "Show all tuning parameters",            cmd_get);
}
