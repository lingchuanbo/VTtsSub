"""
SRT 自动语速同步 TTS 处理器

实现方案：
1. 解析 SRT 文件，获取每句字幕的时间和文本
2. 根据字幕持续时间和文本长度，动态计算每句的语速
3. 调用 TTS 为每句生成独立音频
4. 按时间线拼接音频，保持与字幕同步
"""

import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from typing import List, Callable, Optional


@dataclass
class SubtitleBlock:
    """字幕块"""
    index: int
    start_time: float  # 秒
    end_time: float    # 秒
    text: str
    
    @property
    def duration(self) -> float:
        """持续时间（秒）"""
        return self.end_time - self.start_time
    
    @property
    def char_count(self) -> int:
        """字符数（去除空格和标点）"""
        # 移除标点和空格，只计算实际字符
        clean_text = re.sub(r'[^\w\u4e00-\u9fff]', '', self.text)
        return len(clean_text)


class SRTParser:
    """SRT 文件解析器"""
    
    @staticmethod
    def parse(srt_path: str) -> List[SubtitleBlock]:
        """解析 SRT 文件"""
        with open(srt_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        blocks = []
        # 按空行分割字幕块
        raw_blocks = re.split(r'\n\s*\n', content.strip())
        
        for raw_block in raw_blocks:
            lines = raw_block.strip().split('\n')
            if len(lines) < 3:
                continue
            
            try:
                # 解析序号
                index = int(lines[0].strip())
                
                # 解析时间戳
                time_match = re.match(
                    r'(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[,.](\d{3})',
                    lines[1].strip()
                )
                if not time_match:
                    continue
                
                start_time = SRTParser._timestamp_to_seconds(time_match.groups()[:4])
                end_time = SRTParser._timestamp_to_seconds(time_match.groups()[4:])
                
                # 解析文本（可能多行）
                text = ' '.join(lines[2:]).strip()
                
                blocks.append(SubtitleBlock(
                    index=index,
                    start_time=start_time,
                    end_time=end_time,
                    text=text
                ))
            except (ValueError, IndexError):
                continue
        
        return blocks
    
    @staticmethod
    def _timestamp_to_seconds(parts) -> float:
        """将时间戳转换为秒"""
        h, m, s, ms = map(int, parts)
        return h * 3600 + m * 60 + s + ms / 1000


class SpeedCalculator:
    """语速计算器"""
    
    # 基准参数（可调整）
    BASE_CHARS_PER_SECOND_CN = 4.0   # 中文：每秒约4个字
    BASE_CHARS_PER_SECOND_EN = 12.0  # 英文：每秒约12个字符
    MIN_SPEED = 0.5   # 最小语速
    MAX_SPEED = 2.0   # 最大语速
    
    @staticmethod
    def calculate_speed(block: SubtitleBlock, base_speed: float = 1.0) -> float:
        """
        计算合适的语速
        
        Args:
            block: 字幕块
            base_speed: 基准语速
            
        Returns:
            计算出的语速 (0.5 - 2.0)
        """
        if block.duration <= 0 or block.char_count == 0:
            return base_speed
        
        # 判断是否主要是中文
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', block.text))
        is_chinese = chinese_chars > block.char_count * 0.3
        
        # 选择基准字符速率
        base_rate = (SpeedCalculator.BASE_CHARS_PER_SECOND_CN 
                     if is_chinese 
                     else SpeedCalculator.BASE_CHARS_PER_SECOND_EN)
        
        # 计算需要的字符速率
        required_rate = block.char_count / block.duration
        
        # 计算语速比例
        speed = (required_rate / base_rate) * base_speed
        
        # 限制在合理范围内
        speed = max(SpeedCalculator.MIN_SPEED, min(SpeedCalculator.MAX_SPEED, speed))
        
        return round(speed, 2)


class SRTTTSSync:
    """SRT 同步 TTS 处理器"""
    
    def __init__(self, tts_engine, ffmpeg_path: str = "ffmpeg"):
        """
        Args:
            tts_engine: TTS 引擎实例
            ffmpeg_path: FFmpeg 路径
        """
        self.tts_engine = tts_engine
        self.ffmpeg_path = ffmpeg_path
    
    def generate_synced_audio(
        self,
        srt_path: str,
        output_path: str,
        voice: str = "alloy",
        model_id: str = None,
        base_speed: float = 1.0,
        progress_callback: Optional[Callable[[str], None]] = None
    ) -> str:
        """
        根据 SRT 文件生成同步音频
        
        Args:
            srt_path: SRT 字幕文件路径
            output_path: 输出音频路径
            voice: 语音角色
            model_id: 模型 ID
            base_speed: 基准语速
            progress_callback: 进度回调
            
        Returns:
            输出文件路径
        """
        if progress_callback:
            progress_callback("解析 SRT 文件...")
        
        # 1. 解析 SRT
        blocks = SRTParser.parse(srt_path)
        if not blocks:
            raise ValueError("SRT 文件为空或格式错误")
        
        if progress_callback:
            progress_callback(f"共 {len(blocks)} 条字幕")
        
        # 2. 创建临时目录
        temp_dir = tempfile.mkdtemp(prefix="srt_tts_")
        temp_files = []
        
        try:
            # 3. 为每句字幕生成音频
            for i, block in enumerate(blocks):
                if progress_callback:
                    progress_callback(f"生成音频 [{i+1}/{len(blocks)}]: {block.text[:30]}...")
                
                # 计算语速
                speed = SpeedCalculator.calculate_speed(block, base_speed)
                
                if progress_callback:
                    progress_callback(f"  时长: {block.duration:.2f}s, 语速: {speed}x")
                
                # 生成音频
                temp_audio = os.path.join(temp_dir, f"line_{i:04d}.mp3")
                
                try:
                    self.tts_engine.generate_audio(
                        text=block.text,
                        output_path=temp_audio,
                        voice=voice,
                        model_id=model_id,
                        speed=speed
                    )
                    
                    if os.path.exists(temp_audio):
                        temp_files.append({
                            "path": temp_audio,
                            "start": block.start_time,
                            "end": block.end_time,
                            "duration": block.duration
                        })
                except Exception as e:
                    if progress_callback:
                        progress_callback(f"  警告: 生成失败 - {str(e)}")
            
            if not temp_files:
                raise RuntimeError("没有成功生成任何音频")
            
            # 4. 拼接音频
            if progress_callback:
                progress_callback("拼接音频...")
            
            self._concat_audio_with_timing(temp_files, output_path, progress_callback)
            
            if progress_callback:
                progress_callback(f"完成！输出: {output_path}")
            
            return output_path
            
        finally:
            # 清理临时文件
            import shutil
            try:
                shutil.rmtree(temp_dir)
            except:
                pass
    
    def _concat_audio_with_timing(
        self,
        audio_files: List[dict],
        output_path: str,
        progress_callback: Optional[Callable[[str], None]] = None
    ):
        """
        按时间线拼接音频，保持与字幕同步
        """
        if not audio_files:
            return
        
        # 获取总时长
        total_duration = max(f["end"] for f in audio_files)
        
        # 创建 FFmpeg 复杂滤镜
        # 方案：为每个音频添加延迟，然后混合
        
        temp_dir = os.path.dirname(audio_files[0]["path"])
        
        # 方法1：使用 adelay 滤镜（更精确）
        filter_parts = []
        input_args = []
        
        for i, audio_info in enumerate(audio_files):
            input_args.extend(["-i", audio_info["path"]])
            delay_ms = int(audio_info["start"] * 1000)
            # adelay 滤镜：延迟音频
            filter_parts.append(f"[{i}:a]adelay={delay_ms}|{delay_ms}[a{i}]")
        
        # 混合所有音频
        mix_inputs = "".join(f"[a{i}]" for i in range(len(audio_files)))
        filter_parts.append(f"{mix_inputs}amix=inputs={len(audio_files)}:duration=longest:normalize=0[out]")
        
        filter_complex = ";".join(filter_parts)
        
        # 构建 FFmpeg 命令
        cmd = [self.ffmpeg_path, "-y"]
        cmd.extend(input_args)
        cmd.extend([
            "-filter_complex", filter_complex,
            "-map", "[out]",
            "-c:a", "libmp3lame",
            "-b:a", "192k",
            output_path
        ])
        
        if progress_callback:
            progress_callback(f"执行 FFmpeg 拼接...")
        
        try:
            import sys
            # Windows 下避免编码问题
            startupinfo = None
            creationflags = 0
            if sys.platform == 'win32':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE
                creationflags = subprocess.CREATE_NO_WINDOW
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=False,  # 使用 bytes 避免编码错误
                check=False,
                startupinfo=startupinfo,
                creationflags=creationflags
            )
            
            if result.returncode != 0:
                stderr = result.stderr.decode('utf-8', errors='ignore') if result.stderr else ''
                raise RuntimeError(f"FFmpeg 拼接失败: {stderr[:500]}")
                
        except subprocess.CalledProcessError as e:
            stderr = e.stderr.decode('utf-8', errors='ignore') if e.stderr else str(e)
            raise RuntimeError(f"FFmpeg 拼接失败: {stderr}")
    
    def estimate_audio_duration(self, audio_path: str) -> float:
        """获取音频时长"""
        try:
            import sys
            ffprobe_path = self.ffmpeg_path.replace("ffmpeg", "ffprobe")
            cmd = [
                ffprobe_path,
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                audio_path
            ]
            
            startupinfo = None
            creationflags = 0
            if sys.platform == 'win32':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                creationflags = subprocess.CREATE_NO_WINDOW
            
            result = subprocess.run(
                cmd, 
                capture_output=True, 
                text=False,
                check=True,
                startupinfo=startupinfo,
                creationflags=creationflags
            )
            return float(result.stdout.decode('utf-8', errors='ignore').strip())
        except:
            return 0.0


def generate_synced_audio_from_srt(
    srt_path: str,
    output_path: str,
    engine_type: str = "ttsfm",
    voice: str = "alloy",
    api_key: str = None,
    api_url: str = None,
    model_id: str = None,
    base_speed: float = 1.0,
    ffmpeg_path: str = "ffmpeg",
    progress_callback: Optional[Callable[[str], None]] = None
) -> str:
    """
    便捷函数：从 SRT 生成同步音频
    """
    from video_tool.core.tts_engine import TTSEngine
    
    tts_engine = TTSEngine(
        engine_type=engine_type,
        api_key=api_key,
        api_url=api_url
    )
    
    processor = SRTTTSSync(tts_engine, ffmpeg_path)
    
    return processor.generate_synced_audio(
        srt_path=srt_path,
        output_path=output_path,
        voice=voice,
        model_id=model_id,
        base_speed=base_speed,
        progress_callback=progress_callback
    )
