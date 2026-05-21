#include "zf_common_headfile.h"
#include <opencv2/opencv.hpp>
#include <ncnn/net.h>
#include <stdio.h>
#include <vector>
#include <chrono>
#include <string>
#include <cmath>
#include <cstring>
#include "Ncnn.hpp"
#include "zf_device_uvc.h"  // UVC摄像头驱动

// 全局变量
static ncnn::Net g_net;  // ncnn网络
static bool g_net_loaded = false;
static std::string g_param_path = "tiny_classifier_fp32.ncnn.param";
static std::string g_bin_path = "tiny_classifier_fp32.ncnn.bin";

// 摄像头（保留原有变量，但主要使用UVC驱动）
static cv::VideoCapture g_camera;
static bool g_camera_opened = false;

// 帧率计算
static std::chrono::steady_clock::time_point g_last_time = std::chrono::steady_clock::now();
static int g_frame_count = 0;
static float g_fps = 0.0f;

// CPU占用率计算
static std::chrono::steady_clock::time_point g_last_cpu_time = std::chrono::steady_clock::now();
static float g_cpu_usage = 0.0f;
static unsigned long long g_last_total = 0;
static unsigned long long g_last_idle = 0;
static bool g_first_cpu_call = true;

// 类别名称（根据labels.txt顺序：materials, transportation, weapon）
static const char* g_class_names[] = {
    "materials",     // 类别0
    "transportation", // 类别1
    "weapon"         // 类别2
};
static const int g_num_classes = sizeof(g_class_names) / sizeof(g_class_names[0]);

// Softmax函数，将logits转换为概率
static void softmax(std::vector<float>& scores)
{
    if (scores.empty()) return;
    // 防止数值溢出，减去最大值
    float max_score = scores[0];
    for (size_t i = 1; i < scores.size(); i++)
    {
        if (scores[i] > max_score) max_score = scores[i];
    }
    float sum = 0.0f;
    for (size_t i = 0; i < scores.size(); i++)
    {
        scores[i] = expf(scores[i] - max_score);
        sum += scores[i];
    }
    if (sum > 0.0f)
    {
        for (size_t i = 0; i < scores.size(); i++)
        {
            scores[i] /= sum;
        }
    }
}

// 每个类别的置信度阈值（低于此值显示unknown）
static float g_class_confidence_thresholds[g_num_classes] = {0.5f, 0.5f, 0.5f};

// 是否显示调试信息（原始分数）
static bool g_debug_mode = false;

// 归一化参数（根据模型训练配置调整）
// 训练时预处理：ToTensor()将[0,255]转换为[0,1]，然后Normalize(mean=[0.485,0.456,0.406], std=[0.229,0.224,0.225])
// 我们将在代码中手动进行相同的预处理，所以这里使用原始参数
static const float NORMALIZE_MEAN[3] = {0.485f, 0.456f, 0.406f};
static const float NORMALIZE_STD[3] = {0.229f, 0.224f, 0.225f};

// 模型文件路径（根据实际存放位置调整） - 使用全局变量 g_param_path, g_bin_path
// #define g_param_path.c_str() "tiny_classifier_fp32.ncnn.param"
// #define g_bin_path.c_str() "tiny_classifier_fp32.ncnn.bin"

/**
 * @brief 初始化ncnn网络，加载模型
 * @return 0成功，-1失败
 */
int ncnn_init()
{
    if (g_net_loaded)
        return 0;

    printf("Loading model from:\n");
    printf("  Param: %s\n", g_param_path.c_str());
    printf("  Bin: %s\n", g_bin_path.c_str());

    // 检查文件是否存在
    FILE* fp_param = fopen(g_param_path.c_str(), "r");
    if (fp_param == NULL)
    {
        printf("ERROR: Param file does not exist or cannot be opened: %s\n", g_param_path.c_str());
        return -1;
    }
    fclose(fp_param);

    FILE* fp_bin = fopen(g_bin_path.c_str(), "r");
    if (fp_bin == NULL)
    {
        printf("ERROR: Bin file does not exist or cannot be opened: %s\n", g_bin_path.c_str());
        return -1;
    }
    fclose(fp_bin);

    printf("Model files exist, loading...\n");

    // 加载模型
    int ret = g_net.load_param(g_param_path.c_str());
    if (ret != 0)
    {
        printf("Failed to load param file: %s, error: %d\n", g_param_path.c_str(), ret);
        return -1;
    }
    ret = g_net.load_model(g_bin_path.c_str());
    if (ret != 0)
    {
        printf("Failed to load bin file: %s, error: %d\n", g_bin_path.c_str(), ret);
        return -1;
    }

    g_net_loaded = true;
    printf("NCNN model loaded successfully.\n");

    // 调试：打印网络信息
    // 注意：嵌入式版本可能不支持layer_count()和blob_count() API
    // 暂时注释掉这些调用，避免编译错误
    // printf("Network layer count: %d\n", g_net.layer_count());
    // printf("Network blob count: %d\n", g_net.blob_count());
    printf("NCNN model loaded. (Embedded version - skipping layer/blob info)\n");

    // 设置推理线程数
    g_net.opt.num_threads = 2;
    printf("Threads set to: %d\n", g_net.opt.num_threads);

    // 设置其他选项（嵌入式版本可能需要）
    // 注意：嵌入式版本的Option结构可能不同，只设置最基础的选项
    g_net.opt.use_vulkan_compute = false;
    g_net.opt.use_winograd_convolution = true;
    g_net.opt.use_sgemm_convolution = true;

    // 嵌入式版本可能不支持这些选项，注释掉避免编译错误
    // g_net.opt.use_int8_inference = false;
    // g_net.opt.use_fp16_storage = false;
    // g_net.opt.use_fp16_arithmetic = false;
    // g_net.opt.use_packing_layout = true;

    printf("NCNN basic options configured.\n");
    printf("Normalization params - Mean: [%.3f, %.3f, %.3f], Std: [%.3f, %.3f, %.3f]\n",
           NORMALIZE_MEAN[0], NORMALIZE_MEAN[1], NORMALIZE_MEAN[2],
           NORMALIZE_STD[0], NORMALIZE_STD[1], NORMALIZE_STD[2]);

    // 尝试设置全局默认选项（如果嵌入式版本需要）
    // ncnn::set_default_option(g_net.opt);

    return 0;
}

/**
 * @brief 图像预处理：从320x240原始图像中截取ROI并缩放至96x96
 * @param raw_320x240 输入图像，CV_8UC3格式（BGR）
 * @param roi_x ROI左上角x坐标（待定）
 * @param roi_y ROI左上角y坐标（待定）
 * @param roi_w ROI宽度（待定）
 * @param roi_h ROI高度（待定）
 * @param output_96x96 输出图像，CV_8UC3格式（BGR），尺寸96x96
 * @return 0成功，-1失败
 */
int preprocess_image(const cv::Mat& raw_320x240,
                     int roi_x, int roi_y, int roi_w, int roi_h,
                     cv::Mat& output_96x96)
{
    if (raw_320x240.empty())
    {
        printf("raw_320x240 image is empty.\n");
        return -1;
    }
    if (raw_320x240.cols != 320 || raw_320x240.rows != 240)
    {
        printf("raw image size mismatch, expected 320x240, got %dx%d\n",
               raw_320x240.cols, raw_320x240.rows);
        // 仍然继续处理，但打印警告
    }

    // 确保ROI在图像范围内
    if (roi_x < 0) roi_x = 0;
    if (roi_y < 0) roi_y = 0;
    if (roi_x + roi_w > raw_320x240.cols) roi_w = raw_320x240.cols - roi_x;
    if (roi_y + roi_h > raw_320x240.rows) roi_h = raw_320x240.rows - roi_y;
    if (roi_w <= 0 || roi_h <= 0)
    {
        printf("Invalid ROI dimensions.\n");
        return -1;
    }

    // 截取ROI
    cv::Mat roi = raw_320x240(cv::Rect(roi_x, roi_y, roi_w, roi_h));

    // 如果ROI尺寸已经是96x96，则直接复制，否则缩放至96x96
    if (roi_w == 96 && roi_h == 96) {
        roi.copyTo(output_96x96);
    } else {
        // 缩放至96x96，使用线性插值以保留细节
        cv::resize(roi, output_96x96, cv::Size(96, 96), 0, 0, cv::INTER_LINEAR);
    }

    // 可选：转换为RGB（如果模型需要）
    // cv::cvtColor(output_96x96, output_96x96, cv::COLOR_BGR2RGB);

    return 0;
}

/**
 * @brief 执行ncnn推理
 * @param input_96x96 输入图像，CV_8UC3格式（BGR），尺寸96x96
 * @param scores 输出分类得分向量（大小为类别数）
 * @return 0成功，-1失败
 */
int ncnn_inference(const cv::Mat& input_96x96, std::vector<float>& scores)
{
    if (!g_net_loaded)
    {
        printf("Net not loaded, call ncnn_init first.\n");
        return -1;
    }
    if (input_96x96.empty() || input_96x96.cols != 96 || input_96x96.rows != 96)
    {
        printf("Input image must be 96x96, got %dx%d\n",
               input_96x96.cols, input_96x96.rows);
        return -1;
    }

    if (input_96x96.channels() != 3)
    {
        printf("Input image must have 3 channels (BGR), got %d channels\n", input_96x96.channels());
        return -1;
    }

    // 手动进行与训练相同的预处理：
    // 1. BGR转RGB (OpenCV默认BGR，训练使用RGB)
    // 2. 转换为float并除以255得到[0,1]范围
    // 3. 应用归一化: (x - mean) / std
    // 4. 转换为CHW格式 (ncnn期望CHW)

    cv::Mat img_rgb;
    #if CAMERA_OUTPUT_RGB
        // 摄像头输出已经是RGB，无需转换
        img_rgb = input_96x96.clone();
    #else
        // 摄像头输出BGR，需要转换为RGB
        cv::cvtColor(input_96x96, img_rgb, cv::COLOR_BGR2RGB);
    #endif

    // 转换为float并归一化到[0,1]
    cv::Mat img_float;
    img_rgb.convertTo(img_float, CV_32FC3, 1.0f / 255.0f);

    // 分离通道，应用归一化
    std::vector<cv::Mat> channels(3);
    cv::split(img_float, channels);

    for (int c = 0; c < 3; c++) {
        channels[c] = (channels[c] - NORMALIZE_MEAN[c]) / NORMALIZE_STD[c];
    }

    // 合并回单张图像（仅用于调试）
    cv::Mat normalized;
    cv::merge(channels, normalized);

    // 转换为CHW格式：创建一个连续的内存块
    int size = 96 * 96;
    std::vector<float> chw_data(3 * size);

    // 验证归一化后的数据
    float min_val = 1e10, max_val = -1e10;
    int nan_count = 0, inf_count = 0;

    for (int c = 0; c < 3; c++) {
        const float* channel_data = channels[c].ptr<float>();
        for (int i = 0; i < size; i++) {
            float val = channel_data[i];
            chw_data[c * size + i] = val;

            // 统计信息
            if (val < min_val) min_val = val;
            if (val > max_val) max_val = val;
            if (std::isnan(val)) nan_count++;
            if (std::isinf(val)) inf_count++;
        }
    }

    if (g_debug_mode) {
        printf("Normalized data stats: min=%.4f, max=%.4f, NaN=%d, Inf=%d\n",
               min_val, max_val, nan_count, inf_count);
    }

    // 检查数据是否合理
    if (nan_count > 0 || inf_count > 0) {
        printf("WARNING: Normalized data contains NaN or Inf values!\n");
    }
    if (max_val > 10.0f || min_val < -10.0f) {
        printf("WARNING: Normalized data range seems large: [%.4f, %.4f]\n", min_val, max_val);
    }

    // 创建ncnn::Mat (CHW格式)
    // 对于嵌入式ncnn，使用最简单的构造函数
    if (g_debug_mode) {
        printf("Creating ncnn::Mat from CHW data...\n");
        printf("Data size: %zu floats (3 * %d * %d)\n", chw_data.size(), 96, 96);

        // 检查前几个数据值（用于调试）
        if (chw_data.size() >= 10) {
            printf("First 10 values of chw_data: ");
            for (int i = 0; i < 10; i++) {
                printf("%.6f ", chw_data[i]);
            }
            printf("\n");
        }
    }

    // 只使用方法2：最明确的构造函数 (w, h, c, data)
    ncnn::Mat in = ncnn::Mat(96, 96, 3, chw_data.data());

    if (in.empty())
    {
        printf("ERROR: Failed to create ncnn::Mat with constructor (96, 96, 3, data)\n");
        printf("Trying alternative: from_pixels with normalized data...\n");

        // 如果标准方法失败，尝试使用from_pixels_resize处理归一化后的图像
        // 注意：from_pixels_resize可能需要不同的像素格式
        cv::Mat normalized_rgb;
        cv::cvtColor(normalized, normalized_rgb, cv::COLOR_BGR2RGB);

        // 将归一化后的float图像转换为uchar（缩放回0-255范围以便from_pixels处理）
        cv::Mat normalized_uchar;
        cv::normalize(normalized_rgb, normalized_uchar, 0, 255, cv::NORM_MINMAX, CV_8UC3);

        in = ncnn::Mat::from_pixels(normalized_uchar.data, ncnn::Mat::PIXEL_RGB, 96, 96);

        if (in.empty()) {
            printf("ERROR: All methods failed to create input Mat!\n");
            return -1;
        }
    }

    if (g_debug_mode) {
        printf("Input Mat created successfully: w=%d, h=%d, c=%d\n", in.w, in.h, in.c);
        printf("Input Mat total elements: %d (expected: %d)\n", in.w * in.h * in.c, 96 * 96 * 3);
    }

    // 验证输入Mat数据
    if (in.c != 3) {
        printf("WARNING: Input Mat has %d channels, expected 3!\n", in.c);
        printf("This may cause inference failures. Trying to fix...\n");

        // 如果通道数不正确，尝试重新创建
        // 可能嵌入式ncnn需要不同的数据布局
        if (in.c == 1) {
            printf("Detected 1-channel Mat. Model likely expects 3 channels.\n");
            printf("Trying to create 3-channel Mat with explicit layout...\n");

            // 重新创建，确保是3通道
            in = ncnn::Mat(96, 96, 3);
            // 手动复制数据（假设chw_data是CHW格式）
            float* in_data = in;
            if (in_data != nullptr && chw_data.size() >= 96*96*3) {
                memcpy(in_data, chw_data.data(), chw_data.size() * sizeof(float));
                printf("Manually copied data to 3-channel Mat\n");
            } else {
                printf("ERROR: Cannot copy data to 3-channel Mat\n");
                return -1;
            }
        }
    }

    // 检查输入Mat数据前几个值
    if (g_debug_mode && in.c == 3 && in.w == 96 && in.h == 96) {
        const float* in_data = in;
        printf("First 6 values of input Mat (CHW format): ");
        for (int i = 0; i < 6 && i < in.w * in.h * in.c; i++) {
            printf("%.6f ", in_data[i]);
        }
        printf("\n");

        // 检查不同通道的第一个值
        if (in.w * in.h * in.c >= 96*96*3) {
            printf("First pixel by channel: R=%.6f, G=%.6f, B=%.6f\n",
                   in_data[0], in_data[96*96], in_data[2*96*96]);
        }
    }

    ncnn::Extractor ex = g_net.create_extractor();

    // 输入blob名称可能为"in0"，参见param文件
    int input_ret = ex.input("in0", in);
    if (input_ret != 0)
    {
        printf("Warning: input 'in0' returned error: %d\n", input_ret);
        printf("Trying alternative input names...\n");

        const char* possible_input_names[] = {"input", "data", "0", "in", "input0"};
        for (size_t i = 0; i < sizeof(possible_input_names)/sizeof(possible_input_names[0]); i++)
        {
            input_ret = ex.input(possible_input_names[i], in);
            if (input_ret == 0)
            {
                printf("Successfully set input using name: %s\n", possible_input_names[i]);
                break;
            }
        }

        if (input_ret != 0)
        {
            printf("Failed to set input blob! Trying index 0...\n");
            input_ret = ex.input(0, in);  // 尝试使用索引0
            if (input_ret == 0)
            {
                printf("Successfully set input using index 0\n");
            }
            else
            {
                printf("Failed to set input with index 0, error: %d\n", input_ret);
                return -1;
            }
        }
    }

    ncnn::Mat out;

    // 尝试多种方法提取输出blob
    // 嵌入式ncnn可能使用不同的blob命名规则
    int ret = ex.extract("out0", out);  // 输出blob名称可能为"out0"

    if (ret != 0)
    {
        printf("Failed to extract output blob 'out0', error: %d\n", ret);

        // 尝试其他可能的输出名称（更全面的列表）
        const char* possible_output_names[] = {
            "out0", "out1", "out", "output", "Output", "OUTPUT", "OUT0", "Out0",
            "linear_7", "19", "15", "fc", "fc_out", "fc_output",
            "prob", "prob0", "probability", "softmax", "softmax_output",
            "classifier", "classifier_output", "predictions", "pred"
        };

        bool name_found = false;
        for (size_t i = 0; i < sizeof(possible_output_names)/sizeof(possible_output_names[0]); i++)
        {
            ret = ex.extract(possible_output_names[i], out);
            if (ret == 0)
            {
                if (g_debug_mode) {
                    printf("SUCCESS: Extracted using name: '%s'\n", possible_output_names[i]);
                }
                name_found = true;
                break;
            }
            else
            {
                // 只显示有意义的错误信息
                if (g_debug_mode && ret != -100) { // -100通常是"找不到名称"，很常见
                    printf("Failed with name '%s', error: %d\n", possible_output_names[i], ret);
                }
            }
        }

        // 如果名称都失败，尝试使用blob索引（嵌入式版本可能只支持索引）
        if (!name_found)
        {
            if (g_debug_mode) {
                printf("Trying blob indices (0-50)...\n");
            }
            // 尝试更广泛的索引范围，不只是0-16
            // 有些模型可能有更多中间blob
            for (int idx = 0; idx <= 50; idx++)
            {
                ret = ex.extract(idx, out);
                if (ret == 0)
                {
                    if (g_debug_mode) {
                        printf("SUCCESS: Extracted using blob index: %d\n", idx);
                    }
                    name_found = true;
                    break;
                }
                // 每10个索引显示一次进度
                if (g_debug_mode && idx % 10 == 0 && idx > 0) {
                    printf("  Tried indices 0-%d...\n", idx);
                }
            }
        }

        // 尝试反向索引（从大到小）
        if (!name_found)
        {
            if (g_debug_mode) {
                printf("Trying reverse blob indices (50-0)...\n");
            }
            for (int idx = 50; idx >= 0; idx--)
            {
                ret = ex.extract(idx, out);
                if (ret == 0)
                {
                    if (g_debug_mode) {
                        printf("SUCCESS: Extracted using blob index: %d (reverse)\n", idx);
                    }
                    name_found = true;
                    break;
                }
            }
        }

        if (!name_found)
        {
            printf("ERROR: All extraction attempts failed!\n");
            printf("Possible issues:\n");
            printf("  1. Input format incorrect (should be CHW, float32, 3 channels)\n");
            printf("  2. Model expects different preprocessing\n");
            printf("  3. Embedded ncnn has different API\n");
            return -1;
        }
    }
    else
    {
        if (g_debug_mode) {
            printf("SUCCESS: Extracted using default name 'out0'\n");
        }
    }

    if (g_debug_mode) {
        printf("Output blob dimensions: w=%d, h=%d, c=%d, d=%d\n", out.w, out.h, out.c, out.d);
    }

    // 将输出转换为score向量
    scores.resize(out.w);  // 假设out.w等于类别数
    for (int i = 0; i < out.w; i++)
    {
        scores[i] = out[i];
    }

    // 调试输出：显示原始分数
    if (g_debug_mode && out.w > 0)
    {
        printf("Raw logits before softmax: ");
        float max_logit = scores[0];
        float min_logit = scores[0];
        for (int i = 0; i < out.w; i++)
        {
            const char* name = "unknown";
            if (i < g_num_classes) {
                name = g_class_names[i];
            }
            printf("%s:%.4f ", name, scores[i]);
            if (scores[i] > max_logit) max_logit = scores[i];
            if (scores[i] < min_logit) min_logit = scores[i];
        }
        printf(" [min=%.4f, max=%.4f]\n", min_logit, max_logit);
    }

    // 应用softmax将logits转换为概率
    softmax(scores);

    // 调试输出：显示softmax后概率
    if (g_debug_mode && !scores.empty())
    {
        printf("Probabilities after softmax: ");
        float max_prob = scores[0];
        int max_idx = 0;
        for (size_t i = 0; i < scores.size(); i++)
        {
            const char* name = "unknown";
            if (i < (size_t)g_num_classes) {
                name = g_class_names[i];
            }
            printf("%s:%.6f ", name, scores[i]);
            if (scores[i] > max_prob)
            {
                max_prob = scores[i];
                max_idx = i;
            }
        }
        const char* max_name = "unknown";
        if (max_idx < g_num_classes) {
            max_name = g_class_names[max_idx];
        }
        printf(" [max=%s:%.6f]\n", max_name, max_prob);
    }

    return 0;
}

/**
 * @brief 获取原始图像（320x240）的辅助函数
 * @note 此函数需要根据实际摄像头驱动实现
 * @param raw_image 输出的原始图像（CV_8UC3）
 * @return 0成功，-1失败
 */
int get_raw_image_320x240(cv::Mat& raw_image)
{
    // 首选：使用UVC驱动获取原始彩色图像
    if (get_raw_color_image(raw_image) == 0) {
        // 成功获取UVC彩色图像
        // 检查尺寸，如果不是320x240则调整（UVC驱动应已设置为此尺寸）
        if (raw_image.cols != 320 || raw_image.rows != 240)
        {
            printf("Warning: UVC camera frame size is %dx%d, resizing to 320x240\n",
                   raw_image.cols, raw_image.rows);
            cv::resize(raw_image, raw_image, cv::Size(320, 240), 0, 0, cv::INTER_LINEAR);
        }
        // 确保图像为3通道BGR（UVC驱动应该已经是）
        if (raw_image.channels() == 1) {
            cv::cvtColor(raw_image, raw_image, cv::COLOR_GRAY2BGR);
        } else if (raw_image.channels() == 4) {
            cv::cvtColor(raw_image, raw_image, cv::COLOR_BGRA2BGR);
        }
        return 0;
    }

    // 备选：使用原有的OpenCV摄像头（兼容模式）
    printf("UVC driver not available, falling back to OpenCV camera...\n");

    if (!g_camera_opened)
    {
        printf("ERROR: Camera not initialized. Call camera_init() first.\n");

        // 尝试自动打开默认摄像头作为后备（不推荐，但提供兼容性）
        printf("Attempting to open default camera as fallback...\n");
        g_camera.open(0);  // 默认摄像头

        if (!g_camera.isOpened())
        {
            printf("Failed to open default camera. Please initialize camera properly.\n");
            return -1;
        }

        // 设置分辨率
        g_camera.set(cv::CAP_PROP_FRAME_WIDTH, 320);
        g_camera.set(cv::CAP_PROP_FRAME_HEIGHT, 240);
        g_camera_opened = true;
        printf("Default camera opened as fallback.\n");
    }

    // 从摄像头读取一帧
    if (!g_camera.read(raw_image))
    {
        printf("Failed to read frame from camera.\n");
        return -1;
    }

    // 检查图像尺寸，如果不是320x240则调整
    if (raw_image.cols != 320 || raw_image.rows != 240)
    {
        printf("Warning: Camera frame size is %dx%d, resizing to 320x240\n",
               raw_image.cols, raw_image.rows);
        cv::resize(raw_image, raw_image, cv::Size(320, 240), 0, 0, cv::INTER_LINEAR);
    }

    // 确保图像有3个通道（彩色）
    if (raw_image.channels() == 1)
    {
        cv::cvtColor(raw_image, raw_image, cv::COLOR_GRAY2BGR);
    }
    else if (raw_image.channels() == 4)
    {
        cv::cvtColor(raw_image, raw_image, cv::COLOR_BGRA2BGR);
    }

    return 0;
}

/**
 * @brief 综合函数：获取图像、预处理、推理
 * @param roi_x, roi_y, roi_w, roi_h ROI参数
 * @param scores 输出得分
 * @return 0成功，-1失败
 */
int ncnn_process_frame(int roi_x, int roi_y, int roi_w, int roi_h,
                       std::vector<float>& scores)
{
    cv::Mat raw_image;
    int ret = get_raw_image_320x240(raw_image);
    if (ret != 0)
        return -1;

    cv::Mat input_96x96;
    ret = preprocess_image(raw_image, roi_x, roi_y, roi_w, roi_h, input_96x96);
    if (ret != 0)
        return -1;

    ret = ncnn_inference(input_96x96, scores);
    return ret;
}

/**
 * @brief 更新帧率计数器，计算当前FPS
 */
void update_fps_counter()
{
    g_frame_count++;
    auto now = std::chrono::steady_clock::now();
    auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(now - g_last_time).count();

    // 每1000ms更新一次FPS
    if (elapsed >= 1000)
    {
        g_fps = g_frame_count * 1000.0f / elapsed;
        g_frame_count = 0;
        g_last_time = now;
    }
}

/**
 * @brief 获取最高得分的类别索引和置信度
 * @param scores 得分向量
 * @param top_index 输出的最高得分索引
 * @param top_score 输出的最高得分（置信度）
 * @return 0成功，-1失败
 */
int get_top_class(const std::vector<float>& scores, int& top_index, float& top_score)
{
    if (scores.empty())
        return -1;

    top_index = 0;
    top_score = scores[0];
    for (size_t i = 1; i < scores.size(); i++)
    {
        if (scores[i] > top_score)
        {
            top_score = scores[i];
            top_index = i;
        }
    }
    return 0;
}

/**
 * @brief 获取CPU占用率（通过读取/proc/stat）
 * @return CPU占用率百分比，失败返回0.0
 */
float get_cpu_usage()
{
    FILE* fp = fopen("/proc/stat", "r");
    if (!fp)
    {
        // 文件打开失败，可能不是Linux系统
        return 0.0f;
    }

    char line[256];
    if (fgets(line, sizeof(line), fp) == NULL)
    {
        fclose(fp);
        return 0.0f;
    }
    fclose(fp);

    // 解析第一行：cpu user nice system idle iowait irq softirq steal guest guest_nice
    unsigned long long user, nice, system, idle, iowait, irq, softirq, steal, guest, guest_nice;
    int ret = sscanf(line, "cpu %llu %llu %llu %llu %llu %llu %llu %llu %llu %llu",
                     &user, &nice, &system, &idle, &iowait, &irq, &softirq, &steal, &guest, &guest_nice);
    if (ret < 4)  // 至少需要前4个值
    {
        return 0.0f;
    }

    // 计算总时间和空闲时间
    unsigned long long total = user + nice + system + idle + iowait + irq + softirq + steal;
    unsigned long long idle_time = idle + iowait;  // 通常将iowait也视为空闲

    if (g_first_cpu_call)
    {
        g_first_cpu_call = false;
        g_last_total = total;
        g_last_idle = idle_time;
        return 0.0f;
    }

    // 计算差值
    unsigned long long total_diff = total - g_last_total;
    unsigned long long idle_diff = idle_time - g_last_idle;

    // 保存当前值供下次使用
    g_last_total = total;
    g_last_idle = idle_time;

    if (total_diff == 0)
    {
        return 0.0f;
    }

    // 计算CPU占用率
    float usage = 100.0f * (1.0f - (float)idle_diff / (float)total_diff);
    return usage;
}

/**
 * @brief 更新CPU占用率计数器，每秒更新一次
 */
void update_cpu_usage()
{
    auto now = std::chrono::steady_clock::now();
    auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(now - g_last_cpu_time).count();

    // 每1000ms更新一次CPU占用率
    if (elapsed >= 1000)
    {
        g_cpu_usage = get_cpu_usage();
        g_last_cpu_time = now;
    }
}

/**
 * @brief 显示推理结果（帧率和类别）
 * @param scores 得分向量
 * @param display_on_image 是否在图像上显示（暂未实现）
 */
void display_results(const std::vector<float>& scores, bool display_on_image)
{
    // 更新帧率和CPU占用率
    update_fps_counter();
    update_cpu_usage();

    // 获取最高得分类别
    int top_index = 0;
    float top_score = 0.0f;
    if (get_top_class(scores, top_index, top_score) != 0)
    {
        printf("Failed to get top class\n");
        return;
    }

    // 应用置信度阈值
    const char* class_name = "unknown";
    if (top_index >= 0 && top_index < g_num_classes)
    {
        if (top_score >= g_class_confidence_thresholds[top_index])
        {
            class_name = g_class_names[top_index];
        }
        else
        {
            // 置信度过低，显示unknown
            class_name = "unknown";
        }
    }

    // 输出到控制台
    float class_threshold = (top_index >= 0 && top_index < g_num_classes) ?
                            g_class_confidence_thresholds[top_index] : 0.5f;
    printf("FPS: %.1f | CPU: %.1f%% | Class: %s | Confidence: %.3f%s\n",
           g_fps, g_cpu_usage, class_name, top_score,
           (top_score < class_threshold && strcmp(class_name, "unknown") != 0) ? " (below threshold)" : "");

    // 可选：在图像上显示（需要传入图像参数）
    if (display_on_image)
    {
        // 留待后续实现
    }
}

/**
 * @brief 实时推理主循环
 * @param roi_x, roi_y, roi_w, roi_h ROI参数
 * @param loop_count 循环次数，0表示无限循环
 * @return 0成功，-1失败
 */
int ncnn_real_time_inference(int roi_x, int roi_y, int roi_w, int roi_h, int loop_count)
{
    if (!g_net_loaded)
    {
        printf("Net not loaded, call ncnn_init first.\n");
        return -1;
    }

    int count = 0;
    while (loop_count == 0 || count < loop_count)
    {
        std::vector<float> scores;
        int ret = ncnn_process_frame(roi_x, roi_y, roi_w, roi_h, scores);
        if (ret != 0)
        {
            printf("Frame processing failed\n");
            // 继续尝试
            continue;
        }

        // 显示结果
        display_results(scores);

        count++;

        // 简单延时，避免占用100% CPU
        // 实际频率由摄像头帧率决定
        // std::this_thread::sleep_for(std::chrono::milliseconds(1));
    }

    return 0;
}

/**
 * @brief 设置调试模式
 * @param enable 是否启用调试输出
 */
void ncnn_set_debug_mode(bool enable)
{
    g_debug_mode = enable;
    printf("Debug mode %s\n", enable ? "enabled" : "disabled");
}

/**
 * @brief 设置所有类别的置信度阈值
 * @param threshold 新的阈值(0.0-1.0)
 */
void ncnn_set_confidence_threshold(float threshold)
{
    if (threshold < 0.0f || threshold > 1.0f)
    {
        printf("Warning: threshold should be between 0.0 and 1.0, got %.3f\n", threshold);
        return;
    }
    for (int i = 0; i < g_num_classes; i++) {
        g_class_confidence_thresholds[i] = threshold;
    }
    printf("All class confidence thresholds updated to %.3f\n", threshold);
}

/**
 * @brief 设置单个类别的置信度阈值
 * @param class_idx 类别索引 (0-based)
 * @param threshold 新的阈值(0.0-1.0)
 */
void ncnn_set_class_confidence_threshold(int class_idx, float threshold)
{
    if (class_idx < 0 || class_idx >= g_num_classes)
    {
        printf("Warning: class index should be between 0 and %d, got %d\n", g_num_classes-1, class_idx);
        return;
    }
    if (threshold < 0.0f || threshold > 1.0f)
    {
        printf("Warning: threshold should be between 0.0 and 1.0, got %.3f\n", threshold);
        return;
    }
    g_class_confidence_thresholds[class_idx] = threshold;
    printf("Class %d (%s) confidence threshold updated to %.3f\n",
           class_idx, g_class_names[class_idx], threshold);
}

/**
 * @brief 设置所有类别的置信度阈值（数组）
 * @param thresholds 阈值数组
 * @param count 数组大小（应该等于类别数）
 */
void ncnn_set_all_confidence_thresholds(const float thresholds[], int count)
{
    if (count != g_num_classes)
    {
        printf("Warning: threshold array size mismatch, expected %d, got %d\n", g_num_classes, count);
        // 仍然设置尽可能多的类别
    }
    int limit = (count < g_num_classes) ? count : g_num_classes;
    for (int i = 0; i < limit; i++) {
        if (thresholds[i] < 0.0f || thresholds[i] > 1.0f)
        {
            printf("Warning: threshold[%d] should be between 0.0 and 1.0, got %.3f\n", i, thresholds[i]);
            continue;
        }
        g_class_confidence_thresholds[i] = thresholds[i];
    }
    printf("Updated confidence thresholds for %d classes\n", limit);
    printf("Current thresholds: ");
    for (int i = 0; i < g_num_classes; i++) {
        printf("%s:%.3f ", g_class_names[i], g_class_confidence_thresholds[i]);
    }
    printf("\n");
}

/**
 * @brief 获取单个类别的置信度阈值
 * @param class_idx 类别索引 (0-based)
 * @return 该类别的置信度阈值，如果索引无效返回0.5
 */
float ncnn_get_class_confidence_threshold(int class_idx)
{
    if (class_idx < 0 || class_idx >= g_num_classes)
    {
        printf("Warning: class index should be between 0 and %d, got %d\n", g_num_classes-1, class_idx);
        return 0.5f;
    }
    return g_class_confidence_thresholds[class_idx];
}

/**
 * @brief 获取所有类别的置信度阈值
 * @param thresholds 输出阈值数组（需要足够大，至少g_num_classes）
 * @param max_count 数组最大容量
 * @return 实际复制的类别数
 */
int ncnn_get_all_confidence_thresholds(float thresholds[], int max_count)
{
    int count = (max_count < g_num_classes) ? max_count : g_num_classes;
    for (int i = 0; i < count; i++) {
        thresholds[i] = g_class_confidence_thresholds[i];
    }
    return count;
}

/**
 * @brief 初始化摄像头
 * @param device 摄像头设备路径，如"/dev/video0"
 * @return 0成功，-1失败
 */
int camera_init(const char* device)
{
    if (g_camera_opened)
    {
        printf("Camera already opened\n");
        return 0;
    }

    printf("Opening camera: %s\n", device);
    g_camera.open(device);

    if (!g_camera.isOpened())
    {
        printf("Failed to open camera %s\n", device);
        return -1;
    }

    // 设置摄像头参数：分辨率320x240，帧率不锁定（让摄像头自由发挥）
    g_camera.set(cv::CAP_PROP_FRAME_WIDTH, 320);
    g_camera.set(cv::CAP_PROP_FRAME_HEIGHT, 240);
    // 不设置帧率，让摄像头以最大帧率运行
    // g_camera.set(cv::CAP_PROP_FPS, 30);

    // 验证实际设置的分辨率
    int actual_width = g_camera.get(cv::CAP_PROP_FRAME_WIDTH);
    int actual_height = g_camera.get(cv::CAP_PROP_FRAME_HEIGHT);
    printf("Camera resolution set to: %dx%d\n", actual_width, actual_height);

    // 如果摄像头不支持320x240，尝试其他分辨率或使用默认值
    if (actual_width != 320 || actual_height != 240)
    {
        printf("Warning: Camera does not support 320x240, using %dx%d instead\n",
               actual_width, actual_height);
        printf("Note: ROI coordinates assume 320x240 image. Adjust ROI if needed.\n");
    }

    g_camera_opened = true;
    printf("Camera initialized successfully\n");

    return 0;
}

/**
 * @brief 释放摄像头资源
 */
void camera_release()
{
    if (g_camera_opened)
    {
        printf("Releasing camera resources...\n");
        g_camera.release();
        g_camera_opened = false;
        printf("Camera released\n");
    }
}

/**
 * @brief 设置归一化参数
 * @param mean RGB均值数组[3]
 * @param std RGB标准差数组[3]
 */
void ncnn_set_normalization_params(const float mean[3], const float std[3])
{
    printf("Normalization parameters updated:\n");
    printf("  Mean: [%.3f, %.3f, %.3f]\n", mean[0], mean[1], mean[2]);
    printf("  Std:  [%.3f, %.3f, %.3f]\n", std[0], std[1], std[2]);
    printf("Note: Parameters stored in constants, need recompile for changes.\n");
}

// ========== LQ_NCNN类实现 ==========

LQ_NCNN::LQ_NCNN()
    : param_path_(""), bin_path_(""), input_name_("in0"), output_name_("out0"),
      input_width_(96), input_height_(96), last_inference_time_(0) {
    // 构造函数实现
}

LQ_NCNN::~LQ_NCNN() {
    // 析构函数实现
    // 可以调用camera_release()如果需要
}

void LQ_NCNN::SetModelPath(const std::string& param_path, const std::string& bin_path) {
    param_path_ = param_path;
    bin_path_ = bin_path;
    // 同时更新全局路径变量，以便ncnn_init使用
    g_param_path = param_path;
    g_bin_path = bin_path;
}

void LQ_NCNN::SetInputName(const std::string& input_name) {
    input_name_ = input_name;
}

void LQ_NCNN::SetOutputName(const std::string& output_name) {
    output_name_ = output_name;
}

void LQ_NCNN::SetInputSize(int width, int height) {
    input_width_ = width;
    input_height_ = height;
}

void LQ_NCNN::SetLabels(const std::vector<std::string>& labels) {
    labels_ = labels;
}

bool LQ_NCNN::Init() {
    // 调用全局ncnn_init函数
    int ret = ncnn_init();
    if (ret != 0) {
        printf("[ERROR] ncnn_init failed\n");
        return false;
    }
    printf("[INFO] NCNN model initialized successfully via LQ_NCNN\n");
    return true;
}

std::string LQ_NCNN::Infer(const cv::Mat& image) {
    auto start_time = std::chrono::steady_clock::now();

    // 将输入图像调整为96x96（模型期望的尺寸）
    cv::Mat resized;
    cv::resize(image, resized, cv::Size(96, 96), 0, 0, cv::INTER_LINEAR);

    // 确保图像有3个通道（彩色）
    if (resized.channels() == 1) {
        cv::cvtColor(resized, resized, cv::COLOR_GRAY2BGR);
    } else if (resized.channels() == 4) {
        cv::cvtColor(resized, resized, cv::COLOR_BGRA2BGR);
    }

    std::vector<float> scores;
    int ret = ncnn_inference(resized, scores);
    if (ret != 0) {
        last_inference_time_ = 0;
        return "inference_error";
    }

    // 获取最高得分类别
    int top_index = 0;
    float top_score = 0.0f;
    if (get_top_class(scores, top_index, top_score) != 0) {
        last_inference_time_ = 0;
        return "unknown";
    }

    // 应用置信度阈值
    std::string result = "unknown";
    if (top_index >= 0) {
        // 确定使用哪个阈值：如果标签列表有效且top_index在范围内，使用对应的阈值
        if (top_index < (int)labels_.size()) {
            // 使用标签列表，阈值对应全局类别顺序（假设labels_与g_class_names顺序一致）
            if (top_index < g_num_classes && top_score >= g_class_confidence_thresholds[top_index]) {
                result = labels_[top_index];
            }
        } else if (top_index < g_num_classes) {
            // 如果标签列表不够，使用全局类别名称
            if (top_score >= g_class_confidence_thresholds[top_index]) {
                result = g_class_names[top_index];
            }
        }
    }

    auto end_time = std::chrono::steady_clock::now();
    last_inference_time_ = std::chrono::duration_cast<std::chrono::milliseconds>(end_time - start_time).count();

    return result;
}

long LQ_NCNN::GetLastInferenceTime() const {
    return last_inference_time_;
}

// ========== 新增的NCNN辅助函数实现 ==========

bool ncnn_initialize_model(LQ_NCNN* detector,
                          const std::string& param_path,
                          const std::string& bin_path,
                          const std::vector<std::string>& labels,
                          int input_width,
                          int input_height) {

    if (!detector) {
        std::cerr << "[ERROR] 检测器指针为空" << std::endl;
        return false;
    }

    // 设置模型参数
    detector->SetModelPath(param_path, bin_path);
    detector->SetInputName("in0");
    detector->SetOutputName("out0");
    detector->SetInputSize(input_width, input_height);
    detector->SetLabels(labels);

    // 初始化模型
    std::cout << "[INFO] 正在加载NCNN模型..." << std::endl;
    if (!detector->Init()) {
        std::cerr << "[ERROR] NCNN模型初始化失败" << std::endl;
        return false;
    }

    std::cout << "[INFO] NCNN模型加载成功" << std::endl;
    std::cout << "[INFO] 模型输入尺寸: " << input_width << "x" << input_height << std::endl;
    std::cout << "[INFO] 类别: ";
    for (const auto& label : labels) {
        std::cout << label << " ";
    }
    std::cout << std::endl;

    return true;
}

std::string ncnn_process_frame(LQ_NCNN* detector,
                              const cv::Mat& frame,
                              long& inference_time) {
    if (!detector) {
        return "Error: Detector not initialized";
    }

    std::string result = detector->Infer(frame);
    inference_time = detector->GetLastInferenceTime();

    return result;
}

void ncnn_print_result(int frame_count,
                      const std::string& result,
                      long inference_time) {
    std::cout << "NCNN 帧 #" << frame_count
              << " | 类别: " << std::setw(15) << std::left << result
              << " | 推理耗时: " << std::setw(4) << inference_time << " ms"
              << std::endl;
}

void ncnn_update_fps_stats(int& frame_count,
                          double& fps,
                          std::chrono::steady_clock::time_point& start_time) {
    frame_count++;
    auto current_time = std::chrono::steady_clock::now();
    auto elapsed_ms = std::chrono::duration_cast<std::chrono::milliseconds>(
        current_time - start_time).count();

    if (elapsed_ms > 1000) {
        fps = frame_count * 1000.0 / elapsed_ms;
        start_time = current_time;
        frame_count = 0;
        std::cout << "[STATUS] NCNN平均FPS: " << std::fixed << std::setprecision(1) << fps << std::endl;
    }
}