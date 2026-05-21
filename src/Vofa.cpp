#include "vofa.hpp"
#include "zf_common_headfile.h"
#include <cstring>
#include <limits>

// Vofa+ JustFloat 协议: 将 float 数组以 raw bytes 通过 UDP 发送
// 每个 float = 4 bytes, little-endian
// 每帧末尾附加 float +inf (0x7F800000) 作为帧尾标记，帮助 Vofa+ 定位帧边界

static bool     vofa_ready = false;

// 默认目标: 开发主机 IP (按你的网络环境修改)
static const char *vofa_ip   = "10.218.192.85";
static uint16_t    vofa_port = 1347;

void vofa_init(const char *ip, uint16_t port) {
    vofa_ip   = ip;
    vofa_port = port;

    if (udp_init(vofa_ip, vofa_port) == 0) {
        vofa_ready = true;
        printf("[Vofa] UDP -> %s:%d init ok\n", vofa_ip, vofa_port);
    } else {
        printf("[Vofa] UDP init failed\n");
    }
}

static void send_raw(const float *data, uint8_t channels) {
    if (!vofa_ready) return;

    // 构造发送缓冲: 数据 + 帧尾 (float +inf)
    const uint8_t total = channels + 1;
    float buf[total];
    memcpy(buf, data, channels * sizeof(float));
    buf[channels] = std::numeric_limits<float>::infinity();

    uint32_t len = total * sizeof(float);
    udp_send_data(reinterpret_cast<const char *>(buf), len);
}

void vofa_send(const float *data, uint8_t channels) {
    send_raw(data, channels);
}

// 便捷函数: 固定 4 通道
void vofa_send_single(float ch0, float ch1, float ch2, float ch3) {
    float buf[4] = {ch0, ch1, ch2, ch3};
    send_raw(buf, 4);
}