from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QLineEdit, QPushButton, QFileDialog, 
                             QGroupBox, QComboBox, QProgressBar, QDoubleSpinBox,
                             QSpinBox, QCheckBox)
from PyQt6.QtCore import QThread, pyqtSignal, Qt
from .console_widget import console_info, console_error
import os
import json
import sys
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading


class TTSThread(QThread):
    """Background thread for TTS generation from SRT."""
    progress = pyqtSignal(int, int)
    log = pyqtSignal(str)
    finished = pyqtSignal(bool, str)
    
    def __init__(self, srt_path, output_dir, voice, engine_type, api_key=None, 
                 model_id=None, language_type="Chinese", api_url=None, speed=1.0, threads=1,
                 auto_truncate=False, subtitles=None, auto_speed=False):
        super().__init__()
        self.srt_path = srt_path
        self.output_dir = output_dir
        self.voice = voice
        self.engine_type = engine_type
        self.api_key = api_key
        self.model_id = model_id
        self.language_type = language_type
        self.api_url = api_url
        self.speed = speed
        self.threads = threads
        self.auto_truncate = auto_truncate
        self.subtitles_data = subtitles  # For truncation timing
        self.auto_speed = auto_speed  # 根据字幕时间自动调整语速
        self.progress_lock = threading.Lock()
        self.completed_count = 0
        self.error_occurred = False
        self.error_message = ""
        self.missing_indices = None  # If set, only generate these indices
    
    def parse_srt_time(self, time_str):
        """Parse SRT time format (HH:MM:SS,mmm) to milliseconds."""
        time_str = time_str.strip().replace(',', '.')
        parts = time_str.split(':')
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds = float(parts[2])
        return int((hours * 3600 + minutes * 60 + seconds) * 1000)
    
    def merge_by_timing(self, audio_segments, output_file, ffmpeg_path, truncate_durations=None):
        """Merge audio segments strictly by SRT timing using ffmpeg."""
        import subprocess
        
        # Build filter complex: place each audio at exact start time
        inputs = []
        filter_parts = []
        
        for i, (start_ms, audio_file) in enumerate(audio_segments):
            inputs.extend(['-i', audio_file])
            
            # If truncation is enabled and we have duration info
            if truncate_durations and i < len(truncate_durations) and truncate_durations[i] > 0:
                max_duration_ms = truncate_durations[i]
                # atrim to truncate, then adelay to position
                filter_parts.append(
                    f'[{i}]atrim=0:{max_duration_ms}ms,asetpts=PTS-STARTPTS,adelay={start_ms}|{start_ms}[a{i}]'
                )
            else:
                filter_parts.append(f'[{i}]adelay={start_ms}|{start_ms}[a{i}]')
        
        # Combine all streams
        mix_inputs = ''.join([f'[a{i}]' for i in range(len(audio_segments))])
        filter_parts.append(
            f'{mix_inputs}amix=inputs={len(audio_segments)}:duration=longest:normalize=0:dropout_transition=0[out]'
        )
        
        filter_complex = ';'.join(filter_parts)
        
        cmd = [ffmpeg_path] + inputs + [
            '-filter_complex', filter_complex,
            '-map', '[out]',
            '-y',
            output_file
        ]
        
        mode = "截断模式" if truncate_durations else "标准模式"
        self.log.emit(f"执行 ffmpeg 按时间合成 ({mode})...")
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
        )
        
        if result.returncode != 0:
            self.log.emit(f"ffmpeg 输出: {result.stderr[:300] if result.stderr else ''}")
        
        return output_file
    
    def run(self):
        try:
            from video_tool.core.tts_engine import TTSEngine
            from video_tool.core.subtitle_manager import SubtitleManager
            import subprocess
            
            # Parse SRT file
            self.log.emit(f"解析字幕文件: {self.srt_path}")
            manager = SubtitleManager()
            subtitles = manager.parse_srt(self.srt_path)
            total = len(subtitles)
            self.log.emit(f"共 {total} 条字幕")
            
            # Initialize TTS engine
            engine = TTSEngine(engine_type=self.engine_type, api_key=self.api_key, api_url=self.api_url)
            
            # Create output directory
            os.makedirs(self.output_dir, exist_ok=True)
            
            # Test first subtitle to verify engine works
            first_text = None
            for sub in subtitles:
                if sub['text'].strip():
                    first_text = sub['text'].strip()
                    break
            
            if first_text:
                self.log.emit(f"测试引擎连接...")
                test_file = os.path.join(self.output_dir, "test_connection.mp3")
                try:
                    engine.generate_audio(first_text[:50], test_file, self.voice, self.model_id, self.language_type, self.speed)
                    if os.path.exists(test_file):
                        os.remove(test_file)
                    self.log.emit("引擎连接成功!")
                except Exception as e:
                    self.finished.emit(False, f"引擎连接失败: {e}\n请检查网络连接和参数设置")
                    return
            
            # Prepare tasks for each subtitle
            tasks = []
            
            if self.auto_speed:
                self.log.emit("=" * 50)
                self.log.emit("自动语速模式: 根据字幕时间调整语速")
                self.log.emit(f"{'序号':<6}{'字幕时长':<12}{'文字数':<8}{'计算语速':<10}{'文本预览'}")
                self.log.emit("-" * 50)
            
            for i, sub in enumerate(subtitles):
                text = sub['text'].strip()
                if not text:
                    continue
                
                # If missing_indices is set, only process those
                if self.missing_indices is not None and i not in self.missing_indices:
                    continue
                
                time_range = sub['time_range']
                times = time_range.split('-->')
                start_time_str = times[0].strip()
                end_time_str = times[1].strip() if len(times) > 1 else start_time_str
                start_ms = self.parse_srt_time(start_time_str)
                end_ms = self.parse_srt_time(end_time_str)
                duration_ms = end_ms - start_ms
                output_file = os.path.join(self.output_dir, f"{i+1:03d}.mp3")
                
                # 计算自动语速
                calculated_speed = self.speed  # 默认使用全局语速
                if self.auto_speed and duration_ms > 0:
                    # 估算：中文约每秒4-5个字，英文约每秒3-4个词
                    # 基准：1.0语速下，中文约每秒4个字
                    char_count = len(text.replace('\n', '').replace(' ', ''))
                    # 基准时间：每个字符约250ms (1.0语速)
                    base_time_ms = char_count * 250
                    
                    if base_time_ms > 0:
                        # 计算需要的语速：如果基准时间 > 字幕时长，需要加快
                        calculated_speed = base_time_ms / duration_ms
                        # 限制语速范围 0.5 - 2.5
                        calculated_speed = max(0.5, min(2.5, calculated_speed))
                    
                    duration_sec = duration_ms / 1000
                    text_preview = text[:20].replace('\n', ' ') + ('...' if len(text) > 20 else '')
                    self.log.emit(f"{i+1:<6}{duration_sec:.2f}s{'':<6}{char_count:<8}{calculated_speed:.2f}x{'':<5}{text_preview}")
                
                tasks.append({
                    'index': i,
                    'text': text,
                    'start_ms': start_ms,
                    'duration_ms': duration_ms,
                    'output_file': output_file,
                    'speed': calculated_speed
                })
            
            if self.auto_speed:
                self.log.emit("=" * 50)
            
            if not tasks:
                self.finished.emit(True, "没有需要生成的音频")
                return
            
            audio_segments = []
            failed_tasks = []
            self.completed_count = 0
            self.error_occurred = False
            
            def generate_single(task, retry_count=0):
                """Generate single audio with retry support."""
                max_retries = 2
                task_speed = task.get('speed', self.speed)
                
                try:
                    engine.generate_audio(task['text'], task['output_file'], 
                                        self.voice, self.model_id, self.language_type, task_speed)
                    
                    # Verify file was created and is valid
                    if not os.path.exists(task['output_file']):
                        raise Exception("文件未生成")
                    if os.path.getsize(task['output_file']) < 1000:
                        raise Exception(f"文件过小 ({os.path.getsize(task['output_file'])} bytes)")
                    
                    return (task['start_ms'], task['output_file'], task['index'], task.get('duration_ms', 0))
                    
                except Exception as e:
                    error_msg = f"第{task['index']+1}条失败 (尝试 {retry_count + 1}/{max_retries + 1}): {e}"
                    self.log.emit(error_msg)
                    
                    # Retry logic
                    if retry_count < max_retries:
                        self.log.emit(f"正在重试第{task['index']+1}条...")
                        import time
                        time.sleep(1)
                        return generate_single(task, retry_count + 1)
                    else:
                        with self.progress_lock:
                            failed_tasks.append(task)
                        return None
            
            # Use thread pool for parallel generation
            self.log.emit(f"使用 {self.threads} 个线程并行生成...")
            self.log.emit(f"需要生成 {len(tasks)} 个音频片段")
            
            with ThreadPoolExecutor(max_workers=self.threads) as executor:
                futures = {executor.submit(generate_single, task): task for task in tasks}
                
                for future in as_completed(futures):
                    result = future.result()
                    if result:
                        audio_segments.append(result)
                    
                    with self.progress_lock:
                        self.completed_count += 1
                        self.progress.emit(self.completed_count, len(tasks))
                        task = futures[future]
                        status = "✓" if result else "✗"
                        self.log.emit(f"[{self.completed_count}/{len(tasks)}] {status} {task['text'][:30]}...")
            
            # Report results
            success_count = len(audio_segments)
            failed_count = len(failed_tasks)
            
            if failed_count > 0:
                self.log.emit(f"警告: {failed_count} 个音频片段生成失败")
                self.log.emit(f"失败序号: {', '.join([str(t['index']+1) for t in failed_tasks[:10]])}" +
                             (f" ... (共{failed_count}个)" if failed_count > 10 else ""))
                self.log.emit("提示: 可使用'重新生成失败项'按钮重试")
            
            if success_count == 0:
                self.finished.emit(False, f"所有音频生成失败，请检查网络和API配置")
                return
            
            # Sort by index to maintain order
            audio_segments.sort(key=lambda x: x[2])
            
            # 如果启用了自动语速，打印生成音频时长与字幕时长的对比
            if self.auto_speed and audio_segments:
                self.log.emit("")
                self.log.emit("=" * 60)
                self.log.emit("音频时长对比 (字幕时长 vs 生成时长)")
                self.log.emit(f"{'序号':<6}{'字幕时长':<12}{'生成时长':<12}{'差异':<10}{'状态'}")
                self.log.emit("-" * 60)
                
                from mutagen.mp3 import MP3
                
                for start_ms, audio_file, idx, duration_ms in audio_segments:
                    try:
                        audio = MP3(audio_file)
                        generated_ms = int(audio.info.length * 1000)
                        diff_ms = generated_ms - duration_ms
                        
                        sub_sec = duration_ms / 1000
                        gen_sec = generated_ms / 1000
                        diff_sec = diff_ms / 1000
                        
                        if diff_ms <= 0:
                            status = "✓ 正常"
                        elif diff_ms < 500:
                            status = "⚠ 略长"
                        else:
                            status = "✗ 超时"
                        
                        self.log.emit(f"{idx+1:<6}{sub_sec:.2f}s{'':<6}{gen_sec:.2f}s{'':<6}{diff_sec:+.2f}s{'':<4}{status}")
                    except Exception as e:
                        self.log.emit(f"{idx+1:<6}无法读取音频时长: {e}")
                
                self.log.emit("=" * 60)
            
            audio_segments = [(s[0], s[1]) for s in audio_segments]
            
            # Merge all audio segments strictly by SRT timing
            self.log.emit("按字幕时间严格合成音频...")
            
            base_name = os.path.splitext(os.path.basename(self.srt_path))[0]
            if base_name.endswith('_中文'):
                base_name = base_name[:-3]
            output_file = os.path.join(os.path.dirname(self.srt_path), f"{base_name}_中文.mp3")
            
            if audio_segments:
                # Find ffmpeg path
                ffmpeg_path = "ffmpeg"
                core_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'core')
                local_ffmpeg = os.path.join(core_dir, 'ffmpeg.exe')
                if os.path.exists(local_ffmpeg):
                    ffmpeg_path = local_ffmpeg
                
                # Calculate truncation durations if enabled
                truncate_durations = None
                if self.auto_truncate and self.subtitles_data:
                    truncate_durations = []
                    for i in range(len(audio_segments)):
                        if i + 1 < len(audio_segments):
                            # Duration = next start - current start
                            duration = audio_segments[i + 1][0] - audio_segments[i][0]
                            truncate_durations.append(max(duration, 100))  # Min 100ms
                        else:
                            truncate_durations.append(0)  # Last segment, no truncation
                    self.log.emit(f"启用自动截断，防止音频重叠")
                
                try:
                    output_file = self.merge_by_timing(audio_segments, output_file, ffmpeg_path, truncate_durations)
                    if os.path.exists(output_file):
                        self.log.emit(f"合成音频保存至: {output_file}")
                    else:
                        self.log.emit("警告: 合成文件未生成")
                except Exception as e:
                    self.log.emit(f"合成失败: {e}")
            
            result_msg = f"完成! 成功 {success_count} 个"
            if failed_count > 0:
                result_msg += f", 失败 {failed_count} 个"
            result_msg += f"\n合成音频: {output_file}"
            
            self.finished.emit(True, result_msg)
            
        except Exception as e:
            self.finished.emit(False, f"错误: {str(e)}")


class MergeThread(QThread):
    """Background thread for merging audio files only."""
    log = pyqtSignal(str)
    finished = pyqtSignal(bool, str)
    
    def __init__(self, srt_path, output_dir):
        super().__init__()
        self.srt_path = srt_path
        self.output_dir = output_dir
    
    def parse_srt_time(self, time_str):
        time_str = time_str.strip().replace(',', '.')
        parts = time_str.split(':')
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds = float(parts[2])
        return int((hours * 3600 + minutes * 60 + seconds) * 1000)
    
    def run(self):
        try:
            from video_tool.core.subtitle_manager import SubtitleManager
            import subprocess
            
            self.log.emit(f"解析字幕文件获取时间信息...")
            manager = SubtitleManager()
            subtitles = manager.parse_srt(self.srt_path)
            
            # Collect existing audio files with timing
            audio_segments = []
            for i, sub in enumerate(subtitles):
                text = sub['text'].strip()
                if not text:
                    continue
                
                audio_file = os.path.join(self.output_dir, f"{i+1:03d}.mp3")
                if os.path.exists(audio_file):
                    time_range = sub['time_range']
                    start_time_str = time_range.split('-->')[0].strip()
                    start_ms = self.parse_srt_time(start_time_str)
                    audio_segments.append((start_ms, audio_file))
            
            if not audio_segments:
                self.finished.emit(False, "未找到音频文件，请先生成语音")
                return
            
            self.log.emit(f"找到 {len(audio_segments)} 个音频文件")
            self.log.emit("合成完整音频...")
            
            base_name = os.path.splitext(os.path.basename(self.srt_path))[0]
            if base_name.endswith('_中文'):
                base_name = base_name[:-3]
            output_file = os.path.join(os.path.dirname(self.srt_path), f"{base_name}_中文.mp3")
            
            # Find ffmpeg
            ffmpeg_path = "ffmpeg"
            core_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'core')
            local_ffmpeg = os.path.join(core_dir, 'ffmpeg.exe')
            if os.path.exists(local_ffmpeg):
                ffmpeg_path = local_ffmpeg
            
            # Build filter complex: place each audio at exact start time
            inputs = []
            filter_parts = []
            
            for i, (start_ms, audio_file) in enumerate(audio_segments):
                inputs.extend(['-i', audio_file])
                filter_parts.append(f'[{i}]adelay={start_ms}|{start_ms}[a{i}]')
            
            mix_inputs = ''.join([f'[a{i}]' for i in range(len(audio_segments))])
            filter_parts.append(
                f'{mix_inputs}amix=inputs={len(audio_segments)}:duration=longest:normalize=0:dropout_transition=0[out]'
            )
            
            filter_complex = ';'.join(filter_parts)
            
            cmd = [ffmpeg_path] + inputs + [
                '-filter_complex', filter_complex,
                '-map', '[out]',
                '-y',
                output_file
            ]
            
            self.log.emit("执行 ffmpeg 按时间合成...")
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
            )
            
            if result.returncode != 0:
                self.log.emit(f"ffmpeg: {result.stderr[:200] if result.stderr else ''}")
            
            if os.path.exists(output_file):
                self.finished.emit(True, f"合成完成!\n保存至: {output_file}")
            else:
                self.finished.emit(False, f"合成失败: {result.stderr[:200] if result.stderr else 'unknown'}")
                
        except Exception as e:
            self.finished.emit(False, f"错误: {str(e)}")


class TTSWidget(QWidget):
    CONFIG_FILE = "config.json"
    CONFIG_KEY = "tts_settings"
    
    def __init__(self):
        super().__init__()
        self.init_ui()
        self.thread = None
        self.merge_thread = None
        self.load_settings()

    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # 字幕文件输入
        input_group = QGroupBox("字幕文件 (中文 SRT)")
        input_layout = QHBoxLayout()
        self.input_edit = QLineEdit()
        self.input_edit.setPlaceholderText("选择翻译后的中文字幕文件...")
        self.browse_input_btn = QPushButton("浏览")
        self.browse_input_btn.clicked.connect(self.browse_input)
        input_layout.addWidget(self.input_edit)
        input_layout.addWidget(self.browse_input_btn)
        input_group.setLayout(input_layout)
        
        # TTS 引擎选择
        engine_group = QGroupBox("TTS 引擎")
        engine_layout = QVBoxLayout()
        
        engine_select_layout = QHBoxLayout()
        engine_select_layout.addWidget(QLabel("选择引擎:"))
        self.engine_combo = QComboBox()
        self.engine_combo.addItems([
            "TTSFM (免费)",
            "ElevenLabs (API)",
            "Qwen TTS (API)"
        ])
        self.engine_combo.currentIndexChanged.connect(self.on_engine_changed)
        engine_select_layout.addWidget(self.engine_combo)
        engine_select_layout.addStretch()
        
        api_key_layout = QHBoxLayout()
        api_key_layout.addWidget(QLabel("API Key:"))
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setPlaceholderText("使用 ElevenLabs 或 Qwen 时需要...")
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_edit.setEnabled(False)
        self.api_key_edit.editingFinished.connect(self.save_settings)
        api_key_layout.addWidget(self.api_key_edit)
        
        api_url_layout = QHBoxLayout()
        api_url_layout.addWidget(QLabel("API URL:"))
        self.api_url_edit = QLineEdit()
        self.api_url_edit.setText("https://dashscope-intl.aliyuncs.com/api/v1")
        self.api_url_edit.setEnabled(False)
        self.api_url_edit.editingFinished.connect(self.save_settings)
        api_url_layout.addWidget(self.api_url_edit)
        
        engine_layout.addLayout(engine_select_layout)
        engine_layout.addLayout(api_key_layout)
        engine_layout.addLayout(api_url_layout)
        engine_group.setLayout(engine_layout)
        
        # 语音设置
        voice_group = QGroupBox("语音设置")
        voice_layout = QVBoxLayout()
        
        voice_select_layout = QHBoxLayout()
        voice_select_layout.addWidget(QLabel("选择语音:"))
        self.voice_combo = QComboBox()
        self.update_voice_list()
        self.voice_combo.currentIndexChanged.connect(self.save_settings)
        voice_select_layout.addWidget(self.voice_combo)
        voice_select_layout.addStretch()
        
        model_layout = QHBoxLayout()
        model_layout.addWidget(QLabel("模型:"))
        self.model_combo = QComboBox()
        self.model_combo.addItems(["eleven_multilingual_v2", "eleven_monolingual_v1", "eleven_turbo_v2"])
        self.model_combo.setEnabled(False)
        model_layout.addWidget(self.model_combo)
        model_layout.addStretch()
        
        # 语速控制
        speed_layout = QHBoxLayout()
        speed_layout.addWidget(QLabel("语速:"))
        self.speed_spin = QDoubleSpinBox()
        self.speed_spin.setRange(0.25, 4.0)
        self.speed_spin.setSingleStep(0.1)
        self.speed_spin.setValue(1.0)
        self.speed_spin.setDecimals(2)
        self.speed_spin.valueChanged.connect(self.save_settings)
        speed_layout.addWidget(self.speed_spin)
        speed_layout.addWidget(QLabel("(0.25 - 4.0, 仅 TTSFM)"))
        speed_layout.addStretch()
        
        # 自动语速选项
        auto_speed_layout = QHBoxLayout()
        self.auto_speed_checkbox = QCheckBox("自动语速 (根据字幕时间调整)")
        self.auto_speed_checkbox.setToolTip("根据每条字幕的时间段自动计算语速，确保音频在字幕时间内完成")
        self.auto_speed_checkbox.stateChanged.connect(self.on_auto_speed_changed)
        self.auto_speed_checkbox.stateChanged.connect(self.save_settings)
        auto_speed_layout.addWidget(self.auto_speed_checkbox)
        auto_speed_layout.addStretch()
        
        # 线程数控制
        threads_layout = QHBoxLayout()
        threads_layout.addWidget(QLabel("并行线程:"))
        self.threads_spin = QSpinBox()
        self.threads_spin.setRange(1, 10)
        self.threads_spin.setValue(3)
        self.threads_spin.valueChanged.connect(self.save_settings)
        threads_layout.addWidget(self.threads_spin)
        threads_layout.addWidget(QLabel("(1-10, 建议3-5)"))
        threads_layout.addStretch()
        
        voice_layout.addLayout(voice_select_layout)
        voice_layout.addLayout(model_layout)
        voice_layout.addLayout(speed_layout)
        voice_layout.addLayout(auto_speed_layout)
        voice_layout.addLayout(threads_layout)
        voice_group.setLayout(voice_layout)
        
        # 操作
        operation_group = QGroupBox("操作")
        operation_layout = QVBoxLayout()
        
        btn_layout = QHBoxLayout()
        self.generate_btn = QPushButton("生成语音")
        self.generate_btn.setToolTip("如果已有音频文件则只合并，否则生成并合并")
        self.generate_btn.clicked.connect(self.smart_generate)
        btn_layout.addWidget(self.generate_btn)
        
        self.regenerate_btn = QPushButton("重新生成全部")
        self.regenerate_btn.setToolTip("强制重新生成所有语音片段")
        self.regenerate_btn.clicked.connect(self.force_regenerate)
        btn_layout.addWidget(self.regenerate_btn)
        
        self.regenerate_failed_btn = QPushButton("重新生成失败项")
        self.regenerate_failed_btn.setToolTip("只重新生成缺失或失败的语音片段")
        self.regenerate_failed_btn.clicked.connect(self.regenerate_failed)
        btn_layout.addWidget(self.regenerate_failed_btn)
        
        self.merge_only_btn = QPushButton("仅合并")
        self.merge_only_btn.setToolTip("只合并已有的音频文件")
        self.merge_only_btn.clicked.connect(self.merge_only)
        btn_layout.addWidget(self.merge_only_btn)
        
        btn_layout.addStretch()
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        
        operation_layout.addLayout(btn_layout)
        operation_layout.addWidget(self.progress_bar)
        operation_group.setLayout(operation_layout)
        
        # 添加到主布局
        layout.addWidget(input_group)
        layout.addWidget(engine_group)
        layout.addWidget(voice_group)
        layout.addWidget(operation_group)
        layout.addStretch()
    
    def on_engine_changed(self):
        """当 TTS 引擎切换时更新界面"""
        engine_text = self.engine_combo.currentText()
        
        is_ttsfm = "TTSFM" in engine_text
        is_elevenlabs = "ElevenLabs" in engine_text
        is_qwen = "Qwen" in engine_text
        
        self.api_key_edit.setEnabled(not is_ttsfm)
        self.api_url_edit.setEnabled(is_qwen)
        self.model_combo.setEnabled(is_elevenlabs or is_qwen)
        
        if is_qwen:
            self.model_combo.clear()
            self.model_combo.addItems(["qwen3-tts-flash", "qwen2-audio-turbo"])
        elif is_elevenlabs:
            self.model_combo.clear()
            self.model_combo.addItems(["eleven_multilingual_v2", "eleven_monolingual_v1", "eleven_turbo_v2"])
        
        self.update_voice_list()
        self.save_settings()
    
    def on_auto_speed_changed(self, state):
        """当自动语速选项改变时更新界面"""
        is_auto = state == Qt.CheckState.Checked.value
        self.speed_spin.setEnabled(not is_auto)
        if is_auto:
            self.speed_spin.setToolTip("自动语速模式下，语速将根据字幕时间自动计算")
        else:
            self.speed_spin.setToolTip("")
    
    def update_voice_list(self):
        """根据选择的引擎更新语音列表"""
        self.voice_combo.clear()
        engine_text = self.engine_combo.currentText()
        
        if "ElevenLabs" in engine_text:
            voices = [
                "Rachel - 21m00Tcm4TlvDq8ikWAM",
                "Domi - AZnzlk1XvdvUeBnXmlld",
                "Bella - EXAVITQu4vr4xnSDxMaL",
                "Antoni - ErXwobaYiN019PkySvjV",
                "Josh - TxGEqnHWrfWFTfGW9XjX",
                "Adam - pNInz6obpgDQGcFmaJgB",
            ]
        elif "Qwen" in engine_text:
            voices = ["Cherry", "Stella", "Luna", "Bella", "Alice", "Nancy", "Cindy", "Emily"]
        else:
            # TTSFM voices
            voices = [
                "alloy (中性)",
                "echo (男声)",
                "fable (英式)",
                "onyx (深沉男声)",
                "nova (女声)",
                "shimmer (温柔女声)",
            ]
        self.voice_combo.addItems(voices)

    def browse_input(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择字幕文件", "", 
            "字幕文件 (*.srt);;所有文件 (*.*)"
        )
        if file_path:
            self.input_edit.setText(file_path)
    
    def load_settings(self):
        """Load saved settings."""
        if os.path.exists(self.CONFIG_FILE):
            try:
                with open(self.CONFIG_FILE, 'r', encoding='utf-8') as f:
                    all_config = json.load(f)
                
                config = all_config.get(self.CONFIG_KEY, {})
                engine_index = config.get("engine_index", 0)
                self.engine_combo.setCurrentIndex(engine_index)
                self.api_key_edit.setText(config.get("api_key", ""))
                self.api_url_edit.setText(config.get("api_url", "https://dashscope-intl.aliyuncs.com/api/v1"))
                self.speed_spin.setValue(config.get("speed", 1.0))
                self.threads_spin.setValue(config.get("threads", 3))
                self.auto_speed_checkbox.setChecked(config.get("auto_speed", False))
                
                voice = config.get("voice", "")
                if voice:
                    idx = self.voice_combo.findText(voice, Qt.MatchFlag.MatchContains)
                    if idx >= 0:
                        self.voice_combo.setCurrentIndex(idx)
            except Exception as e:
                self.log(f"加载设置失败: {e}")
    
    def save_settings(self):
        """Save current settings."""
        # 读取现有配置
        all_config = {}
        if os.path.exists(self.CONFIG_FILE):
            try:
                with open(self.CONFIG_FILE, 'r', encoding='utf-8') as f:
                    all_config = json.load(f)
            except:
                pass
        
        # 更新当前模块的配置
        all_config[self.CONFIG_KEY] = {
            "engine_index": self.engine_combo.currentIndex(),
            "api_key": self.api_key_edit.text(),
            "api_url": self.api_url_edit.text(),
            "voice": self.voice_combo.currentText(),
            "speed": self.speed_spin.value(),
            "threads": self.threads_spin.value(),
            "auto_speed": self.auto_speed_checkbox.isChecked()
        }
        
        try:
            with open(self.CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(all_config, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"保存设置失败: {e}")
    
    def check_audio_exists(self, srt_path):
        """Check if audio files already exist for the SRT file."""
        base_path = os.path.splitext(srt_path)[0]
        output_dir = f"{base_path}_audio"
        
        if not os.path.exists(output_dir):
            return False, 0
        
        # Count existing mp3 files
        mp3_files = [f for f in os.listdir(output_dir) if f.endswith('.mp3') and f[:3].isdigit()]
        return len(mp3_files) > 0, len(mp3_files)
    
    def smart_generate(self):
        """Smart generate: merge if audio exists, otherwise generate."""
        srt_path = self.input_edit.text()
        if not srt_path or not os.path.exists(srt_path):
            self.log("请选择有效的字幕文件")
            return
        
        exists, count = self.check_audio_exists(srt_path)
        if exists:
            self.log(f"检测到已有 {count} 个音频文件，执行合并操作...")
            self.merge_only()
        else:
            self.log("未检测到音频文件，开始生成语音...")
            self.force_regenerate()
    
    def merge_only(self):
        """Only merge existing audio files."""
        srt_path = self.input_edit.text()
        if not srt_path or not os.path.exists(srt_path):
            self.log("请选择有效的字幕文件")
            return
        
        base_path = os.path.splitext(srt_path)[0]
        output_dir = f"{base_path}_audio"
        
        exists, count = self.check_audio_exists(srt_path)
        if not exists:
            self.log("未找到音频文件，请先生成语音")
            return
        
        self.set_buttons_enabled(False)
        self.log(f"开始合并 {count} 个音频文件...")
        
        self.merge_thread = MergeThread(srt_path, output_dir)
        self.merge_thread.log.connect(self.log)
        self.merge_thread.finished.connect(self.on_finished)
        self.merge_thread.start()
    
    def force_regenerate(self):
        """Force regenerate all audio files."""
        srt_path = self.input_edit.text()
        if not srt_path or not os.path.exists(srt_path):
            self.log("请选择有效的字幕文件")
            return
        
        engine_text = self.engine_combo.currentText()
        if "ElevenLabs" in engine_text:
            engine_type = "elevenlabs"
        elif "Qwen" in engine_text:
            engine_type = "qwen"
        else:
            engine_type = "ttsfm"
        
        api_key = self.api_key_edit.text().strip()
        if engine_type != "ttsfm" and not api_key:
            self.log("请输入 API Key")
            return
        
        voice_text = self.voice_combo.currentText()
        if engine_type == "elevenlabs":
            parts = voice_text.split(" - ")
            voice = parts[1] if len(parts) > 1 else parts[0]
        elif engine_type == "qwen":
            voice = voice_text
        else:
            voice = voice_text.split(" ")[0]
        
        base_path = os.path.splitext(srt_path)[0]
        output_dir = f"{base_path}_audio"
        
        self.set_buttons_enabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        
        self.log(f"开始生成语音...")
        self.log(f"引擎: {engine_text}")
        self.log(f"语音: {voice_text}")
        self.log(f"输出目录: {output_dir}")
        
        model_id = self.model_combo.currentText() if engine_type not in ["ttsfm"] else None
        api_url = self.api_url_edit.text().strip() if engine_type == "qwen" else None
        
        speed = self.speed_spin.value()
        threads = self.threads_spin.value()
        auto_speed = self.auto_speed_checkbox.isChecked()
        
        if auto_speed:
            self.log(f"语速: 自动 (根据字幕时间调整)")
        else:
            self.log(f"语速: {speed}")
        self.log(f"并行线程: {threads}")
        
        self.thread = TTSThread(
            srt_path, output_dir, voice, engine_type, 
            api_key, model_id, "Chinese", api_url, speed, threads,
            auto_speed=auto_speed
        )
        self.thread.progress.connect(self.on_progress)
        self.thread.log.connect(self.log)
        self.thread.finished.connect(self.on_finished)
        self.thread.start()
    
    def regenerate_failed(self):
        """Regenerate only missing or failed audio files."""
        srt_path = self.input_edit.text()
        if not srt_path or not os.path.exists(srt_path):
            self.log("请选择有效的字幕文件")
            return
        
        # Parse SRT to get all expected files
        from video_tool.core.subtitle_manager import SubtitleManager
        manager = SubtitleManager()
        subtitles = manager.parse_srt(srt_path)
        
        base_path = os.path.splitext(srt_path)[0]
        output_dir = f"{base_path}_audio"
        
        # Check which files are missing or invalid
        missing_indices = []
        for i, sub in enumerate(subtitles):
            if not sub['text'].strip():
                continue
            
            audio_file = os.path.join(output_dir, f"{i+1:03d}.mp3")
            if not os.path.exists(audio_file):
                missing_indices.append(i)
            elif os.path.getsize(audio_file) < 1000:  # Less than 1KB, likely invalid
                self.log(f"检测到无效文件: {i+1:03d}.mp3 (大小: {os.path.getsize(audio_file)} bytes)")
                missing_indices.append(i)
        
        if not missing_indices:
            self.log("✓ 所有音频文件都已存在且有效")
            self.log("如需重新生成，请使用'重新生成全部'按钮")
            return
        
        self.log(f"发现 {len(missing_indices)} 个缺失或无效的音频文件")
        self.log(f"缺失序号: {', '.join([str(i+1) for i in missing_indices[:10]])}" + 
                 (f" ... (共{len(missing_indices)}个)" if len(missing_indices) > 10 else ""))
        
        # Get engine settings
        engine_text = self.engine_combo.currentText()
        if "ElevenLabs" in engine_text:
            engine_type = "elevenlabs"
        elif "Qwen" in engine_text:
            engine_type = "qwen"
        else:
            engine_type = "ttsfm"
        
        api_key = self.api_key_edit.text().strip()
        if engine_type != "ttsfm" and not api_key:
            self.log("请输入 API Key")
            return
        
        voice_text = self.voice_combo.currentText()
        if engine_type == "elevenlabs":
            parts = voice_text.split(" - ")
            voice = parts[1] if len(parts) > 1 else parts[0]
        elif engine_type == "qwen":
            voice = voice_text
        else:
            voice = voice_text.split(" ")[0]
        
        model_id = self.model_combo.currentText() if engine_type not in ["ttsfm"] else None
        api_url = self.api_url_edit.text().strip() if engine_type == "qwen" else None
        speed = self.speed_spin.value()
        threads = self.threads_spin.value()
        auto_speed = self.auto_speed_checkbox.isChecked()
        
        self.set_buttons_enabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        
        self.log(f"开始重新生成失败项...")
        self.log(f"引擎: {engine_text}")
        self.log(f"并行线程: {threads}")
        if auto_speed:
            self.log(f"语速: 自动 (根据字幕时间调整)")
        
        # Create a custom thread for partial regeneration
        self.thread = TTSThread(
            srt_path, output_dir, voice, engine_type, 
            api_key, model_id, "Chinese", api_url, speed, threads,
            auto_truncate=False, subtitles=subtitles, auto_speed=auto_speed
        )
        # Override to only process missing indices
        self.thread.missing_indices = missing_indices
        self.thread.progress.connect(self.on_progress)
        self.thread.log.connect(self.log)
        self.thread.finished.connect(self.on_finished)
        self.thread.start()
    
    def set_buttons_enabled(self, enabled):
        """Enable or disable all operation buttons."""
        self.generate_btn.setEnabled(enabled)
        self.regenerate_btn.setEnabled(enabled)
        self.regenerate_failed_btn.setEnabled(enabled)
        self.merge_only_btn.setEnabled(enabled)
    
    def on_progress(self, current, total):
        percent = int(current / total * 100)
        self.progress_bar.setValue(percent)
    
    def on_finished(self, success, message):
        self.set_buttons_enabled(True)
        self.progress_bar.setVisible(False)
        self.log(message)
        if success:
            self.log("=" * 40)
    
    def log(self, message):
        console_info(message, "TTS语音")
