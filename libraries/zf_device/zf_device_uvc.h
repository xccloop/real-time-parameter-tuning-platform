#ifndef _zf_driver_uvc_h
#define _zf_driver_uvc_h


#include "zf_common_typedef.h"
#include <opencv2/imgproc/imgproc.hpp>  // for cv::cvtColor
#include <opencv2/highgui/highgui.hpp> // for cv::VideoCapture



#define UVC_WIDTH   320
#define UVC_HEIGHT  240
#define UVC_FPS     60


extern cv::Mat First_image;//原始图像 (BGR, 320x240x3)
extern cv::Mat Rgb_image;  //RGB彩色图 (320x240x3)

extern uint8_t *rgb_image;  // RGB图像数据指针 (320*240*3 bytes, R/G/B交错)

int8 uvc_camera_init(const char *path);
int8 wait_image_refresh();

// 供 ncnn 模块调用：获取一帧 320x240 BGR 彩色图像
int8 get_raw_color_image(cv::Mat &raw_image);

using namespace cv;
#endif
