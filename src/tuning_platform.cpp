#include "tuning_platform.hpp"
#include <cstdio>
#include <cstring>

TuningPlatform &TuningPlatform::instance()
{
    static TuningPlatform inst;
    return inst;
}

void TuningPlatform::register_param(const char *name, int *value_ptr,
                                     int min_val, int max_val, const char *desc)
{
    if (count_ >= MAX_PARAMS)
    {
        printf("[tuning] ERROR: max params (%d) reached, cannot register '%s'\n",
               MAX_PARAMS, name);
        return;
    }

    int idx = count_++;
    strncpy(params_[idx].name, name, PARAM_NAME_LEN - 1);
    params_[idx].name[PARAM_NAME_LEN - 1] = '\0';
    params_[idx].value   = *value_ptr;
    params_[idx].min_val = min_val;
    params_[idx].max_val = max_val;
    params_[idx].desc    = desc;
    value_ptrs_[idx]     = value_ptr;
}

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
                return false;
            }
            params_[i].value = value;
            *value_ptrs_[i] = value;   // 同步到外部变量
            printf("[tuning] '%s' = %d   (range: %d ~ %d)\n",
                   name, value, params_[i].min_val, params_[i].max_val);
            return true;
        }
    }
    printf("[tuning] ERROR: parameter '%s' not found\n", name);
    return false;
}

bool TuningPlatform::get_param(const char *name, int *value)
{
    for (int i = 0; i < count_; i++)
    {
        if (strcmp(params_[i].name, name) == 0)
        {
            *value = *value_ptrs_[i];  // 读实际变量
            return true;
        }
    }
    return false;
}

void TuningPlatform::list_params()
{
    if (count_ == 0)
    {
        printf("[tuning] No parameters registered.\n");
        return;
    }

    printf("\n");
    printf("+============================================================+\n");
    printf("|           Real-Time Parameter Tuning Platform              |\n");
    printf("+------+-----------+-----------+-----------+-----------------+\n");
    printf("| Name |   Value   |    Min    |    Max    |   Description   |\n");
    printf("+------+-----------+-----------+-----------+-----------------+\n");

    for (int i = 0; i < count_; i++)
    {
        int val = *value_ptrs_[i];  // 读取实际变量
        printf("| %-4s | %9d | %9d | %9d | %-15s |\n",
               params_[i].name,
               val,
               params_[i].min_val,
               params_[i].max_val,
               params_[i].desc);
    }

    printf("+------+-----------+-----------+-----------+-----------------+\n");
    printf("\nUsage: set <name> <value>   — modify a parameter\n");
    printf("       get                  — refresh this table\n\n");
}

const TuningParam *TuningPlatform::param_at(int idx) const
{
    if (idx < 0 || idx >= count_) return nullptr;
    return &params_[idx];
}
