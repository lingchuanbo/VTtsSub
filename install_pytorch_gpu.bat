@echo off
chcp 65001 >nul
title PyTorch GPU 安装工具

cd /d "%~dp0"

echo ========================================
echo    PyTorch GPU 版本安装工具
echo    使用国内镜像源加速下载
echo ========================================
echo.

:: 检查虚拟环境
if not exist ".venv\Scripts\activate.bat" (
    echo [ERROR] 虚拟环境不存在，请先运行 run_gpu.bat 创建
    pause
    exit /b 1
)

:: 激活虚拟环境
call .venv\Scripts\activate.bat

echo [INFO] 当前 Python 环境:
python --version
echo.

:: 检查当前 PyTorch 版本
echo [INFO] 检查当前 PyTorch 状态...
python -c "import torch; print(f'当前版本: {torch.__version__}'); print(f'CUDA 可用: {torch.cuda.is_available()}')" 2>nul
if errorlevel 1 (
    echo [INFO] PyTorch 未安装
)
echo.

echo ========================================
echo 请选择 CUDA 版本:
echo   1. CUDA 12.1 (推荐，适用于 RTX 30/40 系列)
echo   2. CUDA 11.8 (适用于较旧显卡)
echo   3. 仅卸载 PyTorch
echo   4. 退出
echo ========================================
echo.

set /p choice=请输入选项 (1/2/3/4): 

if "%choice%"=="1" goto cuda121
if "%choice%"=="2" goto cuda118
if "%choice%"=="3" goto uninstall
if "%choice%"=="4" goto end

echo [ERROR] 无效选项
pause
exit /b 1

:uninstall
echo.
echo [INFO] 卸载现有 PyTorch...
pip uninstall torch torchvision torchaudio -y
echo [INFO] 卸载完成
goto end

:cuda121
echo.
echo [INFO] 卸载现有 PyTorch...
pip uninstall torch torchvision torchaudio -y

echo.
echo [INFO] 安装 PyTorch GPU 版本 (CUDA 12.1)...
echo [INFO] 从 PyTorch 官方源下载，请耐心等待...
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
goto verify

:cuda118
echo.
echo [INFO] 卸载现有 PyTorch...
pip uninstall torch torchvision torchaudio -y

echo.
echo [INFO] 安装 PyTorch GPU 版本 (CUDA 11.8)...
echo [INFO] 从 PyTorch 官方源下载，请耐心等待...
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
goto verify

:verify
echo.
echo ========================================
echo [INFO] 验证安装...
echo ========================================
python -c "import torch; print(f'PyTorch 版本: {torch.__version__}'); print(f'CUDA 可用: {torch.cuda.is_available()}'); print(f'CUDA 版本: {torch.version.cuda}' if torch.cuda.is_available() else 'CUDA 不可用'); print(f'GPU: {torch.cuda.get_device_name(0)}' if torch.cuda.is_available() else '')"

if errorlevel 1 (
    echo.
    echo [ERROR] 安装验证失败
) else (
    echo.
    echo [SUCCESS] 安装完成！
)

:end
echo.
pause
