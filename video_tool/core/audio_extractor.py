import os
import subprocess
import threading


class AudioExtractor:
    def __init__(self, ffmpeg_path="ffmpeg"):
        self.ffmpeg_path = ffmpeg_path

    def extract_audio(self, video_path, output_path, format="mp3"):
        """
        从视频文件提取音频
        """
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")

        output_dir = os.path.dirname(output_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        codec_map = {
            "mp3": "libmp3lame",
            "wav": "pcm_s16le",
            "aac": "aac"
        }
        codec = codec_map.get(format, "libmp3lame")

        command = [
            self.ffmpeg_path,
            "-y",
            "-i", video_path,
            "-vn",
            "-acodec", codec,
            output_path
        ]

        subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return True

    def extract_silent_video(self, video_path, output_path, progress_callback=None):
        """
        从视频中移除音频，生成无声视频
        """
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")

        output_dir = os.path.dirname(output_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        command = [
            self.ffmpeg_path,
            "-y",
            "-i", video_path,
            "-an",  # 移除音频
            "-c:v", "copy",  # 直接复制视频流，不重新编码
            output_path
        ]

        subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if progress_callback:
            progress_callback("无声视频生成完成")
        return True


class DemucsProcessor:
    """使用 Demucs 进行人声分离"""
    
    def __init__(self, model="htdemucs", device="cuda"):
        """
        初始化 Demucs 处理器
        
        Args:
            model: 模型名称 (htdemucs, htdemucs_ft, mdx_extra 等)
            device: 设备 (cuda 或 cpu)
        """
        self.model = model
        self.device = device
    
    def separate(self, audio_path, output_dir, progress_callback=None,
                 output_vocals=True, output_accompaniment=True):
        """
        分离音频为人声和伴奏
        
        Args:
            audio_path: 输入音频路径
            output_dir: 输出目录
            progress_callback: 进度回调函数
            output_vocals: 是否输出人声
            output_accompaniment: 是否输出伴奏
            
        Returns:
            dict: 包含 vocals 和 accompaniment 路径的字典
        """
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")
        
        os.makedirs(output_dir, exist_ok=True)
        
        if progress_callback:
            progress_callback("正在加载 Demucs 模型...")
        
        try:
            import torch
            import torchaudio
            
            # 确保 soundfile 后端可用
            try:
                import soundfile
            except ImportError:
                raise ImportError("请安装 soundfile: pip install soundfile")
            
            from demucs.pretrained import get_model
            from demucs.apply import apply_model
            
            # 检测设备
            if self.device == "cuda" and not torch.cuda.is_available():
                self.device = "cpu"
                if progress_callback:
                    progress_callback("CUDA 不可用，使用 CPU 处理")
            
            device = torch.device(self.device)
            
            # 加载模型
            model = get_model(self.model)
            model.to(device)
            model.eval()
            
            if progress_callback:
                progress_callback(f"模型加载完成，使用设备: {self.device}")
                progress_callback("正在处理音频...")
            
            # 加载音频
            wav, sr = torchaudio.load(audio_path)
            
            # 如果采样率不匹配，重采样
            if sr != model.samplerate:
                wav = torchaudio.functional.resample(wav, sr, model.samplerate)
                sr = model.samplerate
            
            # 转换为模型需要的格式
            wav = wav.to(device)
            
            # 确保是立体声
            if wav.shape[0] == 1:
                wav = wav.repeat(2, 1)
            elif wav.shape[0] > 2:
                wav = wav[:2]
            
            # 添加 batch 维度
            wav = wav.unsqueeze(0)
            
            # 应用模型
            with torch.no_grad():
                sources = apply_model(model, wav, device=device, progress=True)
            
            # 获取源名称
            source_names = model.sources
            
            # 保存分离的音频
            base_name = os.path.splitext(os.path.basename(audio_path))[0]
            # 移除 _temp 后缀（如果有）
            if base_name.endswith("_temp"):
                base_name = base_name[:-5]
            results = {}
            
            # 保存人声
            if output_vocals and "vocals" in source_names:
                vocals_idx = source_names.index("vocals")
                vocals = sources[0, vocals_idx].cpu()
                vocals_path = os.path.join(output_dir, f"{base_name}_vocals.wav")
                torchaudio.save(vocals_path, vocals, sr)
                results["vocals"] = vocals_path
                if progress_callback:
                    progress_callback("已保存: vocals (人声)")
            
            # 合并非人声部分作为伴奏
            if output_accompaniment and "vocals" in source_names:
                accompaniment = torch.zeros_like(sources[0, 0])
                for i, name in enumerate(source_names):
                    if name != "vocals":
                        accompaniment += sources[0, i]
                
                accompaniment = accompaniment.cpu()
                accompaniment_path = os.path.join(output_dir, f"{base_name}_accompaniment.wav")
                torchaudio.save(accompaniment_path, accompaniment, sr)
                results["accompaniment"] = accompaniment_path
                if progress_callback:
                    progress_callback("已保存: accompaniment (伴奏)")
            
            if progress_callback:
                progress_callback("人声分离完成！")
            
            return results
            
        except ImportError as e:
            raise ImportError(f"请安装 demucs: pip install demucs\n{str(e)}")
        except Exception as e:
            raise Exception(f"Demucs 处理失败: {str(e)}")


class FullVideoProcessor:
    """完整视频处理：分离人声、伴奏和生成无声视频"""
    
    def __init__(self, ffmpeg_path="ffmpeg", demucs_model="htdemucs", device="cuda"):
        self.ffmpeg_path = ffmpeg_path
        self.audio_extractor = AudioExtractor(ffmpeg_path)
        self.demucs = DemucsProcessor(demucs_model, device)
    
    def process(self, video_path, output_dir, progress_callback=None,
                output_vocals=True, output_accompaniment=True, output_silent_video=True):
        """
        处理视频：提取音频、分离人声/伴奏、生成无声视频
        
        Args:
            video_path: 输入视频路径
            output_dir: 输出目录
            progress_callback: 进度回调函数
            output_vocals: 是否输出人声
            output_accompaniment: 是否输出伴奏
            output_silent_video: 是否输出无声视频
            
        Returns:
            dict: 包含所有输出文件路径的字典
        """
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")
        
        os.makedirs(output_dir, exist_ok=True)
        
        base_name = os.path.splitext(os.path.basename(video_path))[0]
        results = {}
        
        # 计算总步骤数
        need_demucs = output_vocals or output_accompaniment
        total_steps = 1 if need_demucs else 0  # 提取音频
        if need_demucs:
            total_steps += 1  # Demucs 分离
        if output_silent_video:
            total_steps += 1  # 无声视频
        
        current_step = 0
        
        # 1. 提取音频 (如果需要 Demucs 分离)
        if need_demucs:
            current_step += 1
            if progress_callback:
                progress_callback(f"步骤 {current_step}/{total_steps}: 提取音频...")
            
            temp_audio = os.path.join(output_dir, f"{base_name}_temp.wav")
            self.audio_extractor.extract_audio(video_path, temp_audio, "wav")
            results["original_audio"] = temp_audio
            
            if progress_callback:
                progress_callback("音频提取完成")
            
            # 2. 使用 Demucs 分离人声和伴奏
            current_step += 1
            if progress_callback:
                progress_callback(f"步骤 {current_step}/{total_steps}: 分离人声和伴奏...")
            
            separation_results = self.demucs.separate(
                temp_audio, output_dir, progress_callback,
                output_vocals=output_vocals, output_accompaniment=output_accompaniment
            )
            results.update(separation_results)
        
        # 3. 生成无声视频
        if output_silent_video:
            current_step += 1
            if progress_callback:
                progress_callback(f"步骤 {current_step}/{total_steps}: 生成无声视频...")
            
            silent_video = os.path.join(output_dir, f"{base_name}_silent.mp4")
            self.audio_extractor.extract_silent_video(video_path, silent_video, progress_callback)
            results["silent_video"] = silent_video
        
        # 清理临时文件（可选）
        # os.remove(temp_audio)
        
        if progress_callback:
            progress_callback("=" * 40)
            progress_callback("全部处理完成！输出文件：")
            for key, path in results.items():
                if key != "original_audio":  # 不显示临时文件
                    progress_callback(f"  {key}: {os.path.basename(path)}")
        
        return results


if __name__ == "__main__":
    # 测试
    pass
