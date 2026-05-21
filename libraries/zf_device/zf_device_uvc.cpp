
#include "zf_common_headfile.h"
using namespace cv;

// 定义全局变量
cv::Mat First_image;//原始图像 (BGR, 320x240x3)
cv::Mat Rgb_image;  //RGB彩色图 (320x240x3)

uint8_t *rgb_image;     // RGB图像数据指针 (320*240*3 bytes)
VideoCapture cap;

int8 uvc_camera_init(const char *path)
{
    cap.open(path);

    if(!cap.isOpened())
    {
        printf("find uvc camera error.\r\n");
        return -1;
    } 
    else 
    {
        printf("find uvc camera Successfully.\r\n");
    }


    cap.set(CAP_PROP_FRAME_WIDTH, UVC_WIDTH);     // 设置摄像头宽度 320
    cap.set(CAP_PROP_FRAME_HEIGHT, UVC_HEIGHT);    // 设置摄像头高度 240
    cap.set(CAP_PROP_FPS, 120);              // 显示屏幕帧率

    return 0;
}


int8 wait_image_refresh()
{
    try 
    {
        // 阻塞式等待图像刷新
        cap >> First_image;
        if (First_image.empty()) 
        {
            std::cerr << "未获取到有效图像帧" << std::endl;
            return -1;
        }
    } 
    catch (const cv::Exception& e) 
    {
        std::cerr << "OpenCV 异常: " << e.what() << std::endl;
        return -1;
    }

    // BGR -> RGB 转换，输出 320x240 彩色图
    cv::cvtColor(First_image, Rgb_image, cv::COLOR_BGR2RGB);
    rgb_image = reinterpret_cast<uint8_t *>(Rgb_image.ptr(0));

    return 0;
}

// 供 ncnn 模块调用：获取一帧 320x240 BGR 图像
int8 get_raw_color_image(cv::Mat &raw_image)
{
    if (wait_image_refresh() != 0)
        return -1;

    // 返回 BGR 格式（与 First_image 共享数据，避免拷贝）
    First_image.copyTo(raw_image);
    return 0;
}
