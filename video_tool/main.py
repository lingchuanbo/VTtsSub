#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Video Processing Tool - Main Entry Point
"""
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from video_tool.gui.main_window import MainWindow
from video_tool.gui.styles import MODERN_DARK_THEME


def print_system_info():
    """打印系统和 PyTorch 信息"""
    print("=" * 50)
    print("Video Processing Tool - 系统信息")
    print("=" * 50)
    
    try:
        import torch
        print(f"PyTorch 版本: {torch.__version__}")
        print(f"CUDA 可用: {torch.cuda.is_available()}")
        if torch.cuda.is_available():
            print(f"CUDA 版本: {torch.version.cuda}")
            print(f"GPU 设备: {torch.cuda.get_device_name(0)}")
            print(f"GPU 数量: {torch.cuda.device_count()}")
    except ImportError:
        print("PyTorch 未安装")
    except OSError as e:
        print(f"PyTorch 加载失败 (DLL 错误): {e}")
        print("提示: 可能需要重新安装 PyTorch，或检查 CUDA 版本兼容性")
        print("运行: pip uninstall torch torchvision torchaudio")
        print("然后: pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118")
    except Exception as e:
        print(f"PyTorch 检测失败: {e}")
    
    try:
        import torchvision
        print(f"TorchVision 版本: {torchvision.__version__}")
    except ImportError:
        print("TorchVision 未安装")
    except Exception:
        pass  # 如果 torch 失败，这里也会失败
    
    try:
        import torchaudio
        print(f"TorchAudio 版本: {torchaudio.__version__}")
    except ImportError:
        print("TorchAudio 未安装")
    except Exception:
        pass
    
    print("=" * 50)


def main():
    # 打印系统信息
    print_system_info()
    
    # Enable High DPI scaling
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    
    app = QApplication(sys.argv)
    app.setApplicationName("Video Processing Tool")
    app.setApplicationVersion("1.0.0")
    app.setStyleSheet(MODERN_DARK_THEME)
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
