#ifndef VOFA_HPP
#define VOFA_HPP

#include <cstdint>

// Vofa+ 虚拟示波器 — JustFloat 协议 (UDP)

void vofa_init(const char *ip, uint16_t port);
void vofa_send(const float *data, uint8_t channels);
void vofa_send_single(float ch0, float ch1, float ch2, float ch3);

#endif

/*
VOFA+ JustFloat 协议示例代码

#include "vofa.hpp"
#include <cstdio>
#include <cmath>
#include <unistd.h>

int main()
{
    printf("=== Vofa test start ===\n");
    fflush(stdout);//刷新缓冲区的函数

    vofa_init("10.218.192.85", 1347);

    float phase = 0.0f;
    int   count = 0;
    while (1)
    {
        float buf[4] = {
            sinf(phase),
            sinf(phase * 2.0f),
            phase,
            0.5f
        };
        vofa_send(buf, 4);

        printf("[%d] ch0=%+.3f  ch1=%+.3f  ch2=%.3f\n",
               count++, buf[0], buf[1], buf[2]);
        fflush(stdout);

        phase += 0.1f;
        if (phase > 6.283f) phase -= 6.283f;

        usleep(100000);
    }
    return 0;
}
*/