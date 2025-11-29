@echo off
chcp 65001 >nul
title 安装依赖包

echo ========================================
echo   Video Processing Tool - 依赖安装
echo ========================================
echo.

:: 切换到脚本所在目录
cd /d "%~dp0"

:: 检查 Python 是否安装
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] 未检测到 Python，请先安装 Python 3.8 或更高版本
    echo.
    echo 下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [INFO] 检测到 Python 版本:
python --version
echo.

:: 检查虚拟环境是否存在
if not exist ".venv\Scripts\activate.bat" (
    echo [INFO] 虚拟环境不存在，正在创建...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERROR] 创建虚拟环境失败
        pause
        exit /b 1
    )
    echo [SUCCESS] 虚拟环境创建成功
    echo.
) else (
    echo [INFO] 虚拟环境已存在
    echo.
)

:: 激活虚拟环境
echo [INFO] 激活虚拟环境...
call .venv\Scripts\activate.bat

:: 升级 pip
echo [INFO] 升级 pip...
python -m pip install --upgrade pip -i https://mirrors.aliyun.com/simple
echo.

:: 安装依赖
echo [INFO] 开始安装依赖包 (使用清华镜像源)...
echo ----------------------------------------
pip install -r video_tool\requirements.txt -i https://mirrors.aliyun.com/simple
echo ----------------------------------------
echo.

if errorlevel 1 (
    echo [ERROR] 依赖安装失败
    echo.
    echo 可能的解决方案:
    echo 1. 检查网络连接
    echo 2. 使用国内镜像源: pip install -i https://mirrors.aliyun.com/simple -r video_tool\requirements.txt
    echo 3. 手动安装失败的包
    pause
    exit /b 1
)

echo.
echo ========================================
echo   安装完成！
echo ========================================
echo.
echo 已安装的主要包:
pip list | findstr /i "PyQt6 whisper ffmpeg elevenlabs edge-tts"
echo.
echo 提示:
echo - 双击 run.bat 启动程序
echo - 如需使用 Whisper，首次运行会自动下载模型
echo - 如需使用 ElevenLabs，请在配置中设置 API Key
echo.
pause
