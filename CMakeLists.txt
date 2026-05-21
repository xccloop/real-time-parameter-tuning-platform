cmake_minimum_required(VERSION 3.10)
project(Kyl)

if(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/toolchain_path.cmake")
    include(toolchain_path.cmake)
    message(STATUS "Found toolchain path: ${CMAKE_TOOLCHAIN_PATH}")

    set(CMAKE_C_COMPILER "${CMAKE_TOOLCHAIN_PATH}/bin/loongarch64-linux-gnu-gcc")
    set(CMAKE_CXX_COMPILER "${CMAKE_TOOLCHAIN_PATH}/bin/loongarch64-linux-gnu-g++")
    set(CMAKE_SYSTEM_NAME Linux)
    set(CMAKE_SYSTEM_PROCESSOR loongarch64)
endif()

set(CMAKE_CXX_STANDARD 11)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

file(GLOB SRC
    ${PROJECT_SOURCE_DIR}/src/*.cpp
    ${PROJECT_SOURCE_DIR}/libraries/zf_common/*.cpp
    ${PROJECT_SOURCE_DIR}/libraries/zf_device/*.cpp
    ${PROJECT_SOURCE_DIR}/libraries/zf_driver/*.cpp
    ${PROJECT_SOURCE_DIR}/libraries/zf_components/*.cpp
    ${PROJECT_SOURCE_DIR}/libraries/zf_components/*/*.cpp
)

include_directories(
    ${PROJECT_SOURCE_DIR}/include
    ${PROJECT_SOURCE_DIR}/libraries/zf_common
    ${PROJECT_SOURCE_DIR}/libraries/zf_device
    ${PROJECT_SOURCE_DIR}/libraries/zf_driver
    ${PROJECT_SOURCE_DIR}/libraries/zf_components
    ${PROJECT_SOURCE_DIR}/libraries/zf_components/seekfree_assistant
)

set(LOONGSON_DEPS_ROOT "${CMAKE_SOURCE_DIR}/tools/LQ_Dep_libs")

if(EXISTS "${LOONGSON_DEPS_ROOT}/opencv_install")
    include_directories(${LOONGSON_DEPS_ROOT}/opencv_install/include/opencv4)
    link_directories(${LOONGSON_DEPS_ROOT}/opencv_install/lib)
endif()

if(EXISTS "${LOONGSON_DEPS_ROOT}/ncnn_install")
    include_directories(${LOONGSON_DEPS_ROOT}/ncnn_install/include)
    link_directories(${LOONGSON_DEPS_ROOT}/ncnn_install/lib)
endif()

add_executable(main main.cpp ${SRC})

target_link_libraries(main
    opencv_core
    opencv_imgproc
    opencv_highgui
    opencv_videoio
    opencv_imgcodecs
    ncnn
    pthread
    stdc++
)

target_compile_options(main PRIVATE -Wall -Wextra)
target_link_options(main PRIVATE -Wl,-rpath,/usr/lib)
target_compile_definitions(main PRIVATE LQ_HAVE_NCNN)
