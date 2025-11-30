"""FFmpeg 工具函数"""
import os
import sys


def get_ffmpeg_path() -> str:
    """
    获取 ffmpeg.exe 的路径
    优先使用项目根目录下的 ffmpeg.exe
    """
    # 获取项目根目录（run_gpu.bat 所在目录）
    if getattr(sys, 'frozen', False):
        # 打包后的 exe
        base_dir = os.path.dirname(sys.executable)
    else:
        # 开发环境：向上查找到包含 run_gpu.bat 的目录
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    # 检查项目根目录下的 ffmpeg.exe
    ffmpeg_exe = os.path.join(base_dir, "ffmpeg.exe")
    if os.path.exists(ffmpeg_exe):
        return ffmpeg_exe
    
    # 回退：从配置文件读取
    try:
        import json
        config_path = os.path.join(base_dir, "config.json")
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
                path = config.get("ffmpeg_path", "")
                if path and os.path.exists(path):
                    return path
    except:
        pass
    
    # 最后回退：假设在 PATH 中
    return "ffmpeg"


def get_ffprobe_path() -> str:
    """获取 ffprobe.exe 的路径"""
    ffmpeg = get_ffmpeg_path()
    if ffmpeg.endswith("ffmpeg.exe"):
        ffprobe = ffmpeg.replace("ffmpeg.exe", "ffprobe.exe")
        if os.path.exists(ffprobe):
            return ffprobe
    return "ffprobe"
