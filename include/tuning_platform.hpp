#ifndef TUNING_PLATFORM_HPP
#define TUNING_PLATFORM_HPP

// 实时参数调优平台 —— 运行时可读写系统参数
// 通过串口命令修改参数，主循环持续打印，真正实现"在线调参"

#define MAX_PARAMS 16           // 最大参数数量
#define PARAM_NAME_LEN 32       // 参数名最大长度

// 单个可调参数
struct TuningParam
{
    char name[PARAM_NAME_LEN];  // 参数名
    int  value;                 // 当前值
    int  min_val;               // 最小值
    int  max_val;               // 最大值
    const char *desc;           // 参数说明
};

// 参数调优平台（单例）
class TuningPlatform
{
public:
    // 获取单例
    static TuningPlatform &instance();

    // 注册一个可调参数
    // name: 参数名, value_ptr: 指向实际变量的指针, min/max: 范围, desc: 说明
    void register_param(const char *name, int *value_ptr,
                        int min_val, int max_val, const char *desc);

    // 设置参数（按名称）
    // 返回 true 成功, false 参数不存在或值越界
    bool set_param(const char *name, int value);

    // 获取参数值（按名称）
    // 返回 true 成功，value 写出；false 不存在
    bool get_param(const char *name, int *value);

    // 列出所有参数（通过 printf 输出到串口）
    void list_params();

    // 参数数量
    int param_count() const { return count_; }

    // 按索引获取参数指针
    const TuningParam *param_at(int idx) const;

private:
    TuningParam params_[MAX_PARAMS];
    int        *value_ptrs_[MAX_PARAMS];  // 指向外部变量
    int         count_;

    TuningPlatform() : count_(0) {}
    TuningPlatform(const TuningPlatform &) = delete;
    TuningPlatform &operator=(const TuningPlatform &) = delete;
};

#endif
