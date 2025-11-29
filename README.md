# Video Processing Tool

视频处理工具集 - 集成音频提取、语音识别、字幕处理、TTS等功能

## 功能特性

- **音频提取**: 从视频文件中提取音频（支持 MP3/WAV/AAC）
- **语音识别 (ASR)**: 使用 OpenAI Whisper 将音频转为字幕
- **字幕处理**: 加载、翻译、合并双语字幕
- **字幕烧录**: 将字幕永久烧录到视频中
- **文字转语音 (TTS)**: 使用 Edge TTS 生成多语言语音
- **视频转码**: 转换视频格式和压缩

## 快速开始

### 1. 安装依赖

双击 `run.bat` 会自动创建虚拟环境并安装依赖。

或手动安装：
```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r video_tool\requirements.txt
```

### 2. 配置 FFmpeg

首次运行时，在菜单 `File -> Configuration` 中设置 FFmpeg 路径。

如果未安装 FFmpeg，请从 https://ffmpeg.org/download.html 下载。

### 3. 运行程序

双击 `run.bat` 启动程序。

## 模型存储

### Whisper 模型
- 模型自动下载到：`video_tool/models/whisper/`
- 首次使用会自动下载（根据选择的模型大小）
- 模型大小：
  - tiny: ~39 MB（最快，准确度较低）
  - base: ~74 MB（推荐，平衡速度和准确度）
  - small: ~244 MB
  - medium: ~769 MB
  - large: ~1550 MB（最准确，速度较慢）

## 注意事项

### Whisper (语音识别) 依赖问题

如果遇到 PyTorch DLL 错误（`[WinError 1114] 动态链接库(DLL)初始化例程失败`）：

**原因**：PyTorch 的 C++ 依赖库与系统不兼容

**解决方案**：

1. **推荐：使用 ElevenLabs 或第三方 API**（无需 PyTorch）
   - 选择 ElevenLabs ASR 引擎
   - 或配置第三方 API（如 Qwen ASR）

2. **重新安装 PyTorch（CPU 版本）**：
   ```bash
   pip uninstall torch torchvision torchaudio
   pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
   ```

3. **安装 Visual C++ Redistributable**：
   - 下载并安装：https://aka.ms/vs/17/release/vc_redist.x64.exe
   - 这是 PyTorch 的必需依赖

4. **使用 conda 环境**（推荐）：
   ```bash
   conda create -n video_tool python=3.10
   conda activate video_tool
   conda install pytorch torchvision torchaudio cpuonly -c pytorch
   pip install -r video_tool\requirements.txt
   ```

**注意**：其他功能（音频提取、字幕处理、TTS等）不受影响，仍可正常使用

### 首次使用 Whisper

首次使用语音识别时，会自动下载模型文件（约 100MB-3GB，取决于选择的模型）。

## 系统要求

- Python 3.8+
- Windows 10/11
- FFmpeg (用于音视频处理)
- 足够的磁盘空间（用于 Whisper 模型）

## 许可证

MIT License
