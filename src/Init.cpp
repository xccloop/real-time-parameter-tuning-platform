#include "zf_common_headfile.h"
//#include "motor.h"


uint8 beep=0;
uint8 stop_car = 1;
uint8 start_count = 0;

void Interrupt()// жϺ   
{
   
}


void Init_all()
{
    system_delay_ms(500);

    if(uvc_camera_init("/dev/video0") < 0)
    ips200_show_string(0,20,"Carmera Error!!!!!!!!");//   ʼ  UVC    ͷ      ʼ  
    ips200_show_string(0,40,"Motor init done");   
    ips200_full(RGB565_BLUE);
    system_delay_ms(200);
    ips200_clear();
    pit_ms_init(10, Interrupt); // 5ms жϳ ʼ  
}

