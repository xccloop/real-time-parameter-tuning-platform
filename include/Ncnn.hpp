#ifndef NCNN_HPP
#define NCNN_HPP

#include <opencv2/opencv.hpp>
#include <string>
#include <vector>

class LQ_NCNN {
public:
    LQ_NCNN();
    ~LQ_NCNN();
    
    // 设置模型路径
    void SetModelPath(const std::string& param_path, const std::string& bin_path);
    
    // 设置输入输出名称
    void SetInputName(const std::string& input_name);
    void SetOutputName(const std::string& output_name);
    
    // 设置输入尺寸
    void SetInputSize(int width, int height);
    
    // 设置标签
    void SetLabels(const std::vector<std::string>& labels);
    
    // 初始化模型
    bool Init();
    
    // 推理
    std::string Infer(const cv::Mat& image);
    
    // 获取上次推理时间
    long GetLastInferenceTime() const;
    
    // 添加成员变量和私有方法（如果有的话）
    // ...

private:
    // 私有成员变量
    std::string param_path_;
    std::string bin_path_;
    std::string input_name_;
    std::string output_name_;
    int input_width_;
    int input_height_;
    std::vector<std::string> labels_;
    long last_inference_time_;
    // ... 其他私有成员
};

// ========== 新增的NCNN辅助函数声明 ==========
// 初始化NCNN模型
bool ncnn_initialize_model(LQ_NCNN* detector,
                          const std::string& param_path,
                          const std::string& bin_path,
                          const std::vector<std::string>& labels,
                          int input_width = 96,
                          int input_height = 96);

// 处理单帧图像
std::string ncnn_process_frame(LQ_NCNN* detector, 
                              const cv::Mat& frame, 
                              long& inference_time);

// 打印推理结果
void ncnn_print_result(int frame_count, 
                      const std::string& result, 
                      long inference_time);

// 更新FPS统计
void ncnn_update_fps_stats(int& frame_count, 
                          double& fps,
                          std::chrono::steady_clock::time_point& start_time);

// ========== NCNN C-style函数声明 (来自car目录) ==========
// 初始化ncnn网络，加载模型
int ncnn_init();

// 图像预处理：从原始图像中截取ROI并缩放至112x112
int preprocess_image(const cv::Mat& raw_image,
                     int roi_x, int roi_y, int roi_w, int roi_h,
                     cv::Mat& output_112x112);

// 执行ncnn推理
int ncnn_inference(const cv::Mat& input_112x112, std::vector<float>& scores);

// 设置调试模式
void ncnn_set_debug_mode(bool enable);

// 设置置信度阈值
void ncnn_set_confidence_threshold(float threshold);
// 设置单个类别的置信度阈值
void ncnn_set_class_confidence_threshold(int class_idx, float threshold);
// 设置所有类别的置信度阈值（数组）
void ncnn_set_all_confidence_thresholds(const float thresholds[], int count);
// 获取单个类别的置信度阈值
float ncnn_get_class_confidence_threshold(int class_idx);
// 获取所有类别的置信度阈值
int ncnn_get_all_confidence_thresholds(float thresholds[], int max_count);

// 设置归一化参数
void ncnn_set_normalization_params(const float mean[3], const float std[3]);

// 实时推理主循环
int ncnn_real_time_inference(int roi_x, int roi_y, int roi_w, int roi_h, int loop_count = 0);

// 获取最高得分的类别索引和置信度
int get_top_class(const std::vector<float>& scores, int& top_index, float& top_score);

// 显示推理结果
void display_results(const std::vector<float>& scores, bool display_on_image = false);


#endif // NCNN_HPP