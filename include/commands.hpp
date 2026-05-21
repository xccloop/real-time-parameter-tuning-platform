#ifndef COMMANDS_HPP
#define COMMANDS_HPP

#include "shell.hpp"

// 将所有内置命令注册到 shell
void register_builtin_commands(Shell &shell);

// 全局可调参数（外部变量声明，在 main.cpp 中定义）
extern int g_param_speed;   // 目标速度
extern int g_param_kp;      // PID 比例系数
extern int g_param_ki;      // PID 积分系数
extern int g_param_kd;      // PID 微分系数

#endif
