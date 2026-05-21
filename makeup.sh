echo "make"
clear
make

echo "upload"
current_path=$(pwd) 
remote_host="192.168.58.169" #MOBAXTERM的ip

ping -c 1 -W 3 $remote_host > /dev/null # 3秒

if [ $? -ne 0 ]; then
    echo "设备不在线，上传失败！"
    exit 1
fi

scp -r "$current_path/main" root@$remote_host:/home/root/

if [ $? -eq 0 ]; then
    echo "上传成功"
else
    echo "上传失败"
fi


