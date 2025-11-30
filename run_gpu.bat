@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
title Video Processing Tool (GPU)

echo ========================================
echo   Video Processing Tool - 启动检查
echo ========================================

:: 切换到脚本所在目录
cd /d "%~dp0"

:: 检查 Python
echo.
echo [检查] Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] Python 未找到，请先安装 Python
    pause
    exit /b 1
)
python --version

:: 检查 FFmpeg
echo.
echo [检查] FFmpeg...
set "FFMPEG_EXE=%~dp0ffmpeg.exe"

if exist "!FFMPEG_EXE!" (
    echo [OK] FFmpeg 已找到
    "!FFMPEG_EXE!" -version 2>&1 | findstr /i "ffmpeg version"
) else (
    echo [警告] ffmpeg.exe 未找到
    echo 位置: !FFMPEG_EXE!
    echo.
    echo 请选择：
    echo   1. 自动下载 FFmpeg
    echo   2. 跳过
    echo.
    set /p "choice=请输入选项 (1/2): "
    
    if "!choice!"=="1" (
        call :install_ffmpeg
        if errorlevel 1 (
            echo [错误] FFmpeg 下载失败
            pause
            exit /b 1
        )
    )
)

:: 检查虚拟环境
echo.
echo [检查] 虚拟环境...
if not exist ".venv\Scripts\activate.bat" (
    echo [信息] 虚拟环境不存在，正在创建...
    python -m venv .venv
    if errorlevel 1 (
        echo [错误] 创建虚拟环境失败
        pause
        exit /b 1
    )
)

:: 激活虚拟环境
call .venv\Scripts\activate.bat
echo [OK] 虚拟环境已激活

:: 检查 PyQt6
echo.
echo [检查] PyQt6...
python -c "import PyQt6" >nul 2>&1
if errorlevel 1 (
    echo [信息] PyQt6 未安装，正在安装...
    pip install PyQt6
)
echo [OK] PyQt6 已就绪

:: 检查 soundfile (torchaudio 后端)
echo.
echo [检查] soundfile...
python -c "import soundfile" >nul 2>&1
if errorlevel 1 (
    echo [信息] soundfile 未安装，正在安装...
    pip install soundfile
)
echo [OK] soundfile 已就绪

:: 检查 PyTorch CUDA
echo.
echo [检查] PyTorch CUDA...
python -c "import torch; print(f'PyTorch {torch.__version__}'); print(f'CUDA 可用: {torch.cuda.is_available()}')" 2>nul
if errorlevel 1 (
    echo [警告] PyTorch 未安装或检查失败
    echo 如需 GPU 加速，请运行 install_pytorch_gpu.bat
)

:: 更新配置文件中的 ffmpeg 路径
if exist "!FFMPEG_EXE!" (
    python -c "import json; c=json.load(open('config.json','r',encoding='utf-8')); c['ffmpeg_path']=r'%~dp0ffmpeg.exe'; json.dump(c,open('config.json','w',encoding='utf-8'),indent=4,ensure_ascii=False)" 2>nul
)

:: 启动程序
echo.
echo ========================================
echo   启动程序...
echo ========================================
python -m video_tool.main

echo.
echo 程序已退出
pause
exit /b 0

:: ========================================
:: FFmpeg 自动下载函数
:: ========================================
:install_ffmpeg
echo.
echo ========================================
echo   正在下载 FFmpeg...
echo ========================================

set "FFMPEG_URL=https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
set "FFMPEG_ZIP=%TEMP%\ffmpeg.zip"
set "FFMPEG_TEMP=%TEMP%\ffmpeg_temp"

:: 下载 FFmpeg
echo [下载] 正在从 GitHub 下载 FFmpeg...
echo.

powershell -Command "& {[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; $ProgressPreference = 'SilentlyContinue'; Invoke-WebRequest -Uri '!FFMPEG_URL!' -OutFile '!FFMPEG_ZIP!'}"

if not exist "!FFMPEG_ZIP!" (
    echo [错误] 下载失败，请检查网络连接
    exit /b 1
)

echo [下载] 下载完成
echo [解压] 正在解压...

:: 解压
powershell -Command "& {Expand-Archive -Path '!FFMPEG_ZIP!' -DestinationPath '!FFMPEG_TEMP!' -Force}"

:: 复制 ffmpeg.exe 和 ffprobe.exe 到项目根目录
for /d %%D in ("!FFMPEG_TEMP!\ffmpeg-*") do (
    copy "%%D\bin\ffmpeg.exe" "%~dp0" >nul
    copy "%%D\bin\ffprobe.exe" "%~dp0" >nul
)

:: 清理
del "!FFMPEG_ZIP!" 2>nul
rmdir /s /q "!FFMPEG_TEMP!" 2>nul

:: 验证
if exist "%~dp0ffmpeg.exe" (
    echo.
    echo [OK] FFmpeg 下载成功！
    "%~dp0ffmpeg.exe" -version 2>&1 | findstr /i "ffmpeg version"
    exit /b 0
) else (
    echo [错误] FFmpeg 下载失败
    exit /b 1
)
