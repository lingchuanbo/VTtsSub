import os
import subprocess
import tempfile


class VideoComposer:
    """视频合成器：合并视频、背景音乐、字幕、配音"""
    
    def __init__(self, ffmpeg_path="ffmpeg"):
        self.ffmpeg_path = ffmpeg_path
    
    def compose(self, video_path=None, bgm_path=None, subtitle_path=None, 
                voice_path=None, output_path=None, 
                bgm_volume=0.3, voice_volume=1.0,
                progress_callback=None):
        """
        合成视频
        
        Args:
            video_path: 输入视频路径（必需）
            bgm_path: 背景音乐路径（可选）
            subtitle_path: 字幕文件路径 .srt/.ass（可选）
            voice_path: 配音音频路径（可选）
            output_path: 输出视频路径
            bgm_volume: 背景音乐音量 (0.0-1.0)
            voice_volume: 配音音量 (0.0-1.0)
            progress_callback: 进度回调函数
            
        Returns:
            str: 输出文件路径
        """
        if not video_path or not os.path.exists(video_path):
            raise FileNotFoundError("视频文件不存在")
        
        # 生成输出路径
        if not output_path:
            base_name = os.path.splitext(video_path)[0]
            output_path = f"{base_name}_处理完成.mp4"
        
        output_dir = os.path.dirname(output_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
        
        # 检查哪些输入是有效的
        has_bgm = bgm_path and os.path.exists(bgm_path)
        has_subtitle = subtitle_path and os.path.exists(subtitle_path)
        has_voice = voice_path and os.path.exists(voice_path)
        
        if progress_callback:
            progress_callback(f"输入视频: {video_path}")
            if has_bgm:
                progress_callback(f"背景音乐: {bgm_path}")
            if has_subtitle:
                progress_callback(f"字幕文件: {subtitle_path}")
            if has_voice:
                progress_callback(f"配音文件: {voice_path}")
            progress_callback("-" * 40)
        
        # 构建 ffmpeg 命令
        cmd = [self.ffmpeg_path, "-y"]
        
        # 输入文件
        cmd.extend(["-i", video_path])
        
        input_index = 1
        bgm_index = None
        voice_index = None
        
        if has_bgm:
            cmd.extend(["-i", bgm_path])
            bgm_index = input_index
            input_index += 1
        
        if has_voice:
            cmd.extend(["-i", voice_path])
            voice_index = input_index
            input_index += 1
        
        # 构建滤镜
        filter_complex = []
        audio_outputs = []
        
        # 处理音频混合
        if has_bgm or has_voice:
            # 获取视频原始音频（如果有的话，先静音处理）
            if has_voice:
                # 如果有配音，使用配音替代原声
                if has_bgm:
                    # 配音 + 背景音乐
                    filter_complex.append(
                        f"[{voice_index}:a]volume={voice_volume}[voice];"
                        f"[{bgm_index}:a]volume={bgm_volume}[bgm];"
                        f"[voice][bgm]amix=inputs=2:duration=first:dropout_transition=2[aout]"
                    )
                else:
                    # 仅配音
                    filter_complex.append(
                        f"[{voice_index}:a]volume={voice_volume}[aout]"
                    )
            else:
                # 仅背景音乐，与原视频音频混合
                filter_complex.append(
                    f"[0:a][{bgm_index}:a]amix=inputs=2:duration=first:dropout_transition=2,"
                    f"volume={1.0 + bgm_volume}[aout]"
                )
        
        # 处理字幕
        video_filter = None
        if has_subtitle:
            # 转换路径格式（Windows 需要转义）
            sub_path = subtitle_path.replace("\\", "/").replace(":", "\\:")
            video_filter = f"subtitles='{sub_path}'"
        
        # 构建完整命令
        if filter_complex or video_filter:
            full_filter = []
            
            if video_filter:
                full_filter.append(f"[0:v]{video_filter}[vout]")
            
            if filter_complex:
                full_filter.extend(filter_complex)
            
            cmd.extend(["-filter_complex", ";".join(full_filter)])
            
            # 映射输出
            if video_filter:
                cmd.extend(["-map", "[vout]"])
            else:
                cmd.extend(["-map", "0:v"])
            
            if filter_complex:
                cmd.extend(["-map", "[aout]"])
            else:
                cmd.extend(["-map", "0:a?"])
        else:
            # 无滤镜，直接复制
            cmd.extend(["-c", "copy"])
        
        # 输出编码设置
        if filter_complex or video_filter:
            cmd.extend([
                "-c:v", "libx264",
                "-preset", "medium",
                "-crf", "23",
                "-c:a", "aac",
                "-b:a", "192k"
            ])
        
        cmd.append(output_path)
        
        if progress_callback:
            progress_callback("开始合成视频...")
            progress_callback(f"命令: {' '.join(cmd)}")
        
        try:
            result = subprocess.run(
                cmd, 
                check=True, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE,
                encoding='utf-8',
                errors='ignore'  # 忽略编码错误
            )
            
            if progress_callback:
                progress_callback("视频合成完成！")
                progress_callback(f"输出文件: {output_path}")
            
            return output_path
            
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr if e.stderr else str(e)
            raise Exception(f"FFmpeg 处理失败: {error_msg}")
    
    def compose_simple(self, video_path, output_path, 
                       bgm_path=None, subtitle_path=None, voice_path=None,
                       bgm_volume=0.3, voice_volume=1.0,
                       progress_callback=None):
        """
        简化的合成方法，分步处理避免复杂滤镜
        """
        temp_files = []
        current_video = video_path
        
        try:
            # 步骤1: 添加配音（替换原音轨）
            if voice_path and os.path.exists(voice_path):
                if progress_callback:
                    progress_callback("步骤: 添加配音...")
                
                temp_voice = tempfile.mktemp(suffix=".mp4")
                temp_files.append(temp_voice)
                
                cmd = [
                    self.ffmpeg_path, "-y",
                    "-i", current_video,
                    "-i", voice_path,
                    "-c:v", "copy",
                    "-map", "0:v:0",
                    "-map", "1:a:0",
                    "-shortest",
                    temp_voice
                ]
                subprocess.run(cmd, check=True, capture_output=True,
                             encoding='utf-8', errors='ignore')
                current_video = temp_voice
            
            # 步骤2: 添加背景音乐
            if bgm_path and os.path.exists(bgm_path):
                if progress_callback:
                    progress_callback("步骤: 添加背景音乐...")
                
                temp_bgm = tempfile.mktemp(suffix=".mp4")
                temp_files.append(temp_bgm)
                
                cmd = [
                    self.ffmpeg_path, "-y",
                    "-i", current_video,
                    "-i", bgm_path,
                    "-filter_complex",
                    f"[0:a]volume=1.0[a1];[1:a]volume={bgm_volume}[a2];[a1][a2]amix=inputs=2:duration=first[aout]",
                    "-map", "0:v",
                    "-map", "[aout]",
                    "-c:v", "copy",
                    "-c:a", "aac",
                    temp_bgm
                ]
                subprocess.run(cmd, check=True, capture_output=True,
                             encoding='utf-8', errors='ignore')
                current_video = temp_bgm
            
            # 步骤3: 添加字幕（烧录）
            if subtitle_path and os.path.exists(subtitle_path):
                if progress_callback:
                    progress_callback("步骤: 烧录字幕...")
                
                temp_sub = tempfile.mktemp(suffix=".mp4")
                temp_files.append(temp_sub)
                
                sub_path = subtitle_path.replace("\\", "/").replace(":", "\\:")
                
                cmd = [
                    self.ffmpeg_path, "-y",
                    "-i", current_video,
                    "-vf", f"subtitles='{sub_path}'",
                    "-c:v", "libx264",
                    "-preset", "medium",
                    "-crf", "23",
                    "-c:a", "copy",
                    temp_sub
                ]
                subprocess.run(cmd, check=True, capture_output=True,
                             encoding='utf-8', errors='ignore')
                current_video = temp_sub
            
            # 最终输出
            if current_video == video_path:
                # 没有任何处理，直接复制
                if progress_callback:
                    progress_callback("无需处理，复制原文件...")
                
                import shutil
                shutil.copy2(video_path, output_path)
            else:
                # 复制最终结果
                import shutil
                shutil.copy2(current_video, output_path)
            
            if progress_callback:
                progress_callback("=" * 40)
                progress_callback(f"合成完成: {output_path}")
            
            return output_path
            
        finally:
            # 清理临时文件
            for temp_file in temp_files:
                try:
                    if os.path.exists(temp_file):
                        os.remove(temp_file)
                except:
                    pass


    def compose_advanced(self, video_path, output_path, 
                        bgm_path=None, subtitle_path=None, 
                        voice_path=None, voice_volume=1.0,  # 兼容旧接口
                        voice_tracks=None,  # 新接口：[(path, volume), ...]
                        bgm_volume=0.3,
                        subtitle_config=None,
                        progress_callback=None):
        """
        高级合成方法，支持字幕样式配置和多音轨
        
        Args:
            voice_tracks: 音轨列表 [(path, volume), ...]，支持多个音频混合
            voice_path: 单个配音路径（兼容旧接口）
            voice_volume: 单个配音音量（兼容旧接口）
        """
        temp_files = []
        temp_ass_files = []
        current_video = video_path
        subtitle_config = subtitle_config or {}
        
        # 兼容旧接口：如果没有 voice_tracks 但有 voice_path
        if not voice_tracks and voice_path:
            voice_tracks = [(voice_path, voice_volume)]
        
        # 过滤有效的音轨
        valid_tracks = []
        if voice_tracks:
            for track in voice_tracks:
                if track and len(track) >= 2 and track[0] and os.path.exists(track[0]):
                    valid_tracks.append(track)
        
        try:
            # 步骤1: 添加配音（支持多音轨混合）
            if valid_tracks:
                if progress_callback:
                    progress_callback(f"步骤: 添加配音 ({len(valid_tracks)} 个音轨)...")
                
                temp_voice = tempfile.mktemp(suffix=".mp4")
                temp_files.append(temp_voice)
                
                if len(valid_tracks) == 1:
                    # 单音轨
                    voice_path, voice_vol = valid_tracks[0]
                    cmd = [
                        self.ffmpeg_path, "-y",
                        "-i", current_video,
                        "-i", voice_path,
                        "-filter_complex", f"[1:a]volume={voice_vol}[aout]",
                        "-c:v", "copy",
                        "-map", "0:v:0",
                        "-map", "[aout]",
                        "-shortest",
                        temp_voice
                    ]
                else:
                    # 多音轨混合
                    cmd = [self.ffmpeg_path, "-y", "-i", current_video]
                    
                    # 添加所有音频输入
                    for path, _ in valid_tracks:
                        cmd.extend(["-i", path])
                    
                    # 构建混音滤镜
                    filter_parts = []
                    for i, (_, vol) in enumerate(valid_tracks):
                        filter_parts.append(f"[{i+1}:a]volume={vol}[a{i}]")
                    
                    # 混合所有音轨
                    mix_inputs = "".join(f"[a{i}]" for i in range(len(valid_tracks)))
                    filter_parts.append(f"{mix_inputs}amix=inputs={len(valid_tracks)}:duration=longest[aout]")
                    
                    filter_complex = ";".join(filter_parts)
                    
                    cmd.extend([
                        "-filter_complex", filter_complex,
                        "-c:v", "copy",
                        "-map", "0:v:0",
                        "-map", "[aout]",
                        "-shortest",
                        temp_voice
                    ])
                
                subprocess.run(cmd, check=True, capture_output=True,
                             encoding='utf-8', errors='ignore')
                current_video = temp_voice
            
            # 步骤2: 添加背景音乐
            if bgm_path and os.path.exists(bgm_path):
                if progress_callback:
                    progress_callback("步骤: 添加背景音乐...")
                
                temp_bgm = tempfile.mktemp(suffix=".mp4")
                temp_files.append(temp_bgm)
                
                cmd = [
                    self.ffmpeg_path, "-y",
                    "-i", current_video,
                    "-i", bgm_path,
                    "-filter_complex",
                    f"[0:a]volume=1.0[a1];[1:a]volume={bgm_volume}[a2];[a1][a2]amix=inputs=2:duration=first[aout]",
                    "-map", "0:v",
                    "-map", "[aout]",
                    "-c:v", "copy",
                    "-c:a", "aac",
                    temp_bgm
                ]
                subprocess.run(cmd, check=True, capture_output=True,
                             encoding='utf-8', errors='ignore')
                current_video = temp_bgm
            
            # 步骤3: 添加字幕（烧录）with 样式
            if subtitle_path and os.path.exists(subtitle_path):
                if progress_callback:
                    progress_callback("步骤: 烧录字幕...")
                
                temp_sub = tempfile.mktemp(suffix=".mp4")
                temp_files.append(temp_sub)
                
                # 构建字幕滤镜（可能生成临时 ASS 文件）
                sub_filter = self._build_subtitle_filter(subtitle_path, subtitle_config)
                
                # 检查是否生成了临时 ASS 文件（从滤镜字符串中提取）
                import re
                match = re.search(r"ass='([^']+)'", sub_filter)
                if match:
                    ass_path = match.group(1).replace("\\:", ":").replace("\\'", "'")
                    if os.path.exists(ass_path):
                        temp_ass_files.append(ass_path)
                
                cmd = [
                    self.ffmpeg_path, "-y",
                    "-i", current_video,
                    "-vf", sub_filter,
                    "-c:v", "libx264",
                    "-preset", "medium",
                    "-crf", "23",
                    "-c:a", "copy",
                    temp_sub
                ]
                
                if progress_callback:
                    subtitle_type = subtitle_config.get('type', '单语')
                    primary_size = subtitle_config.get('font_size', 24)
                    secondary_size = subtitle_config.get('secondary_font_size', 18)
                    if subtitle_type == "双语":
                        progress_callback(f"字幕样式: {subtitle_config.get('font', 'default')}, 主字幕: {primary_size}, 副字幕: {secondary_size}")
                    else:
                        progress_callback(f"字幕样式: {subtitle_config.get('font', 'default')}, 大小: {primary_size}")
                
                subprocess.run(cmd, check=True, capture_output=True,
                             encoding='utf-8', errors='ignore')
                current_video = temp_sub
            
            # 最终输出
            if current_video == video_path:
                # 没有任何处理，直接复制
                if progress_callback:
                    progress_callback("无需处理，复制原文件...")
                
                import shutil
                shutil.copy2(video_path, output_path)
            else:
                # 复制最终结果
                import shutil
                shutil.copy2(current_video, output_path)
            
            if progress_callback:
                progress_callback("=" * 40)
                progress_callback(f"合成完成: {output_path}")
            
            return output_path
            
        finally:
            # 清理临时文件
            for temp_file in temp_files:
                try:
                    if os.path.exists(temp_file):
                        os.remove(temp_file)
                except:
                    pass
            
            # 清理临时 ASS 文件
            for temp_ass in temp_ass_files:
                try:
                    if os.path.exists(temp_ass):
                        os.remove(temp_ass)
                except:
                    pass
    
    def _build_subtitle_filter(self, subtitle_path, config):
        """构建字幕滤镜"""
        font_name = config.get("font", "Arial")
        font_size = config.get("font_size", 24)
        secondary_size = config.get("secondary_font_size", 18)
        color = config.get("color", "&HFFFFFF&")
        border = config.get("border_width", 2)
        bold = 1 if config.get("bold", True) else 0
        subtitle_type = config.get("type", "自动检测")
        
        # 如果是双语字幕且副字幕大小不同，需要转换为 ASS 格式
        if subtitle_type == "双语" and secondary_size != font_size:
            # 转换 SRT 为 ASS 以支持不同大小
            ass_path = self._convert_bilingual_to_ass(
                subtitle_path, font_name, font_size, secondary_size, 
                color, border, bold
            )
            # 对于 ASS 滤镜，需要正确转义路径
            sub_path = self._escape_ffmpeg_path(ass_path)
            return f"ass='{sub_path}'"
        else:
            # 单语字幕或相同大小，使用简单方式
            sub_path = self._escape_ffmpeg_path(subtitle_path)
            style = f"FontName={font_name},FontSize={font_size},PrimaryColour={color},OutlineColour=&H000000&,BorderStyle=1,Outline={border},Bold={bold}"
            return f"subtitles='{sub_path}':force_style='{style}'"
    
    def _escape_ffmpeg_path(self, path):
        """转义 FFmpeg 滤镜中的路径"""
        # 转换为正斜杠
        path = path.replace("\\", "/")
        # 转义特殊字符：冒号、单引号、反斜杠、方括号
        path = path.replace(":", "\\:")
        path = path.replace("'", "\\'")
        path = path.replace("[", "\\[")
        path = path.replace("]", "\\]")
        return path
    
    def _convert_bilingual_to_ass(self, srt_path, font_name, primary_size, secondary_size, color, border, bold):
        """将双语 SRT 转换为 ASS 格式，支持不同字体大小"""
        import re
        
        # 读取 SRT 文件
        with open(srt_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 解析 SRT
        blocks = re.split(r'\n\s*\n', content.strip())
        
        # 创建 ASS 文件（使用临时目录避免路径问题）
        ass_path = tempfile.mktemp(suffix='_bilingual.ass')
        
        # ASS 文件头
        bold_val = -1 if bold else 0
        ass_content = f"""[Script Info]
Title: Bilingual Subtitles
ScriptType: v4.00+
WrapStyle: 0
PlayResX: 1920
PlayResY: 1080
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Primary,{font_name},{primary_size},{color},&H000000FF,&H00000000,&H00000000,{bold_val},0,0,0,100,100,0,0,1,{border},0,2,10,10,10,1
Style: Secondary,{font_name},{secondary_size},{color},&H000000FF,&H00000000,&H00000000,{bold_val},0,0,0,100,100,0,0,1,{border},0,2,10,10,10,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        
        # 转换每个字幕块
        for block in blocks:
            lines = block.strip().split('\n')
            if len(lines) < 3:
                continue
            
            # 解析时间
            time_line = lines[1]
            time_match = re.match(r'(\d{2}):(\d{2}):(\d{2}),(\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2}),(\d{3})', time_line)
            if not time_match:
                continue
            
            # 转换为 ASS 时间格式
            start_h, start_m, start_s, start_ms = time_match.groups()[:4]
            end_h, end_m, end_s, end_ms = time_match.groups()[4:]
            
            start_time = f"{start_h}:{start_m}:{start_s}.{start_ms[:2]}"
            end_time = f"{end_h}:{end_m}:{end_s}.{end_ms[:2]}"
            
            # 获取字幕文本
            text_lines = lines[2:]
            
            if len(text_lines) >= 2:
                # 双语字幕：第一行用 Primary 样式，第二行用 Secondary 样式
                primary_text = text_lines[0].strip()
                secondary_text = text_lines[1].strip()
                
                # 使用 ASS 标签组合两行 (注意：\r 后面直接跟样式名，不需要反斜杠)
                combined_text = f"{{\\rPrimary}}{primary_text}\\N{{\\rSecondary}}{secondary_text}"
                
                ass_content += f"Dialogue: 0,{start_time},{end_time},Primary,,0,0,0,,{combined_text}\n"
            else:
                # 单行字幕
                text = text_lines[0].strip() if text_lines else ""
                ass_content += f"Dialogue: 0,{start_time},{end_time},Primary,,0,0,0,,{text}\n"
        
        # 写入 ASS 文件
        with open(ass_path, 'w', encoding='utf-8') as f:
            f.write(ass_content)
        
        return ass_path


if __name__ == "__main__":
    # 测试
    composer = VideoComposer()
