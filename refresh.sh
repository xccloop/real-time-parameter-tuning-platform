rm -rf build
echo "delete finish"
mkdir build
cd build
cp -p /home/luv/opencv/install/my_zf/makeup.sh /home/luv/opencv/install/my_zf/build
echo "copy finish"
cmake -DCMAKE_TOOLCHAIN_FILE=../rv1103.cmake ..