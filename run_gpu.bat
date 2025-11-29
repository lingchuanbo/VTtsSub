@echo off
chcp 65001 >nul
title Video Processing Tool (GPU)

:: 切换到脚本所在目录
cd /d "%~dp0"

:: 设置 GPU 相关环境变量
set CUDA_VISIBLE_DEVICES=0
set PYTORCH_CUDA_ALLOC_CONF=max_split_size_mb:512
set FORCE_CUDA=1

:: 检查虚拟环境是否存在
if not exist ".venv\Scripts\activate.bat" (
    echo [INFO] 虚拟环境不存在，正在创建...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERROR] 创建虚拟环境失败，请确保已安装 Python
        pause
        exit /b 1
    )
)

:: 激活虚拟环境
call .venv\Scripts\activate.bat

:: 检查 PyTorch 是否为 GPU 版本
python -c "import torch; exit(0 if torch.cuda.is_available() else 1)" >nul 2>&1
if errorlevel 1 (
    echo [INFO] 检测到 CPU 版本的 PyTorch 或未安装，正在安装 GPU 版本...
    echo [INFO] 卸载现有 PyTorch...
    pip uninstall torch torchvision torchaudio -y >nul 2>&1
    echo [INFO] 安装 PyTorch GPU 版本 (CUDA 12.0)...
    pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
    if errorlevel 1 (
        echo [ERROR] 安装 PyTorch GPU 版本失败
        pause
        exit /b 1
    )
)

:: 检查其他依赖是否已安装
pip show PyQt6 >nul 2>&1
if errorlevel 1 (
    echo [INFO] 安装其他依赖...
    pip install PyQt6 openai-whisper ffmpeg-python requests ttsfm elevenlabs dashscope srt demucs soundfile -i https://pypi.tuna.tsinghua.edu.cn/simple
    if errorlevel 1 (
        echo [ERROR] 安装依赖失败
        pause
        exit /b 1
    )
)

:: 检查 soundfile 是否已安装（torchaudio 音频后端）
pip show soundfile >nul 2>&1
if errorlevel 1 (
    echo [INFO] 安装 soundfile (torchaudio 音频后端)...
    pip install soundfile -i https://pypi.tuna.tsinghua.edu.cn/simple
)

:: 检查 CUDA 是否可用
echo [INFO] 检查 GPU 状态...
python -c "import torch; print(f'CUDA Available: {torch.cuda.is_available()}'); print(f'CUDA Device: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else \"N/A\"}')"

:: 运行程序
echo [INFO] 启动 Video Processing Tool (GPU 模式)...
python -m video_tool.main

:: 如果程序异常退出，暂停显示错误
if errorlevel 1 (
    echo.
    echo [ERROR] 程序异常退出
    pause
)
