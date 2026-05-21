@echo off
echo ============================================
echo  Real-Time Parameter Tuning Platform
echo  Windows Host Monitor — 安装
echo ============================================
echo.

echo [1/2] 检查 Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo 错误: 未找到 Python！请先安装 Python 3.7+
    echo 下载: https://www.python.org/downloads/
    pause
    exit /b 1
)
python --version
echo.

echo [2/2] 安装依赖包...
python -m pip install pyserial rich
if %errorlevel% neq 0 (
    echo 安装失败，请尝试手动安装:
    echo   pip install pyserial rich
    pause
    exit /b 1
)
echo.

echo ============================================
echo  安装完成！
echo.
echo  使用方法:
echo    python monitor.py -l         列出可用串口
echo    python monitor.py COM3       连接板子（替换COM3为实际串口号）
echo ============================================
pause
