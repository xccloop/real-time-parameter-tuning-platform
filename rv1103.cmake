set(CMAKE_SYSTEM_NAME Linux)
set(CMAKE_SYSTEM_PROCESSOR loongson)
set(tools /opt/loongson-gnu-toolchain-8.3-x86_64-loongarch64-linux-gnu-rc1.3-1/) # 交叉编译器目录

set(CMAKE_C_COMPILER ${tools}/bin/loongarch64-linux-gnu-gcc) # GCC编译器
set(CMAKE_CXX_COMPILER ${tools}/bin/loongarch64-linux-gnu-g++) # G++编译器，注意这里的斜线和g++的写法
set(CMAKE_AR ${tools}/bin/loongarch64-linux-gnu-ar) # AR工具
set(CMAKE_RANLIB ${tools}/bin/loongarch64-linux-gnu-ranlib) # RANLIB工具

set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE ONLY)