from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QLineEdit, QPushButton, QFileDialog, QGroupBox,
                             QSlider, QDoubleSpinBox, QComboBox,
                             QSpinBox, QCheckBox, QProgressBar)
from PyQt6.QtCore import QThread, pyqtSignal, Qt
from .console_widget import console_info, console_error
import os


class ComposerThread(QThread):
    """视频合成线程"""
    finished = pyqtSignal(bool, str)
    progress = pyqtSignal(str)
    
    def __init__(self, video_path, output_path, bgm_path, subtitle_path, 
                 voice_path, bgm_volume, voice_volume, ffmpeg_path):
        super().__init__()
        self.video_path = video_path
        self.output_path = output_path
        self.bgm_path = bgm_path
        self.subtitle_path = subtitle_path
        self.voice_path = voice_path
        self.bgm_volume = bgm_volume
        self.voice_volume = voice_volume
        self.ffmpeg_path = ffmpeg_path
    
    def run(self):
        try:
            from video_tool.core.video_composer import VideoComposer
            
            composer = VideoComposer(self.ffmpeg_path)
            composer.compose_advanced(
                video_path=self.video_path,
                output_path=self.output_path,
                bgm_path=self.bgm_path if self.bgm_path else None,
                subtitle_path=self.subtitle_path if self.subtitle_path else None,
                voice_path=self.voice_path if self.voice_path else None,
                bgm_volume=self.bgm_volume,
                voice_volume=self.voice_volume,
                progress_callback=lambda msg: self.progress.emit(msg)
            )
            
            self.finished.emit(True, "视频合成完成！")
        except Exception as e:
            import traceback
            self.finished.emit(False, f"错误: {str(e)}\n{traceback.format_exc()}")


class VideoComposerWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()
        self.thread = None
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # 视频输入
        video_group = QGroupBox("视频文件 (必需)")
        video_layout = QHBoxLayout()
        self.video_edit = QLineEdit()
        self.video_edit.setPlaceholderText("选择视频文件...")
        self.video_btn = QPushButton("浏览")
        self.video_btn.clicked.connect(self.browse_video)
        video_layout.addWidget(self.video_edit)
        video_layout.addWidget(self.video_btn)
        video_group.setLayout(video_layout)
        
        # 背景音乐
        bgm_group = QGroupBox("背景音乐 (可选)")
        bgm_layout = QVBoxLayout()
        
        bgm_file_layout = QHBoxLayout()
        self.bgm_edit = QLineEdit()
        self.bgm_edit.setPlaceholderText("选择背景音乐文件，留空则忽略...")
        self.bgm_btn = QPushButton("浏览")
        self.bgm_btn.clicked.connect(self.browse_bgm)
        self.bgm_clear_btn = QPushButton("清除")
        self.bgm_clear_btn.clicked.connect(lambda: self.bgm_edit.clear())
        bgm_file_layout.addWidget(self.bgm_edit)
        bgm_file_layout.addWidget(self.bgm_btn)
        bgm_file_layout.addWidget(self.bgm_clear_btn)
        
        bgm_vol_layout = QHBoxLayout()
        bgm_vol_layout.addWidget(QLabel("音量:"))
        self.bgm_volume = QDoubleSpinBox()
        self.bgm_volume.setRange(0.0, 1.0)
        self.bgm_volume.setSingleStep(0.1)
        self.bgm_volume.setValue(0.3)
        bgm_vol_layout.addWidget(self.bgm_volume)
        bgm_vol_layout.addStretch()
        
        bgm_layout.addLayout(bgm_file_layout)
        bgm_layout.addLayout(bgm_vol_layout)
        bgm_group.setLayout(bgm_layout)
        
        # 字幕设置
        subtitle_group = QGroupBox("字幕设置 (可选)")
        subtitle_layout = QVBoxLayout()
        
        # 字幕文件选择
        subtitle_file_layout = QHBoxLayout()
        subtitle_file_layout.addWidget(QLabel("字幕文件:"))
        self.subtitle_edit = QLineEdit()
        self.subtitle_edit.setPlaceholderText("选择字幕文件 (.srt/.ass)，留空则忽略...")
        self.subtitle_btn = QPushButton("浏览")
        self.subtitle_btn.clicked.connect(self.browse_subtitle)
        self.subtitle_clear_btn = QPushButton("清除")
        self.subtitle_clear_btn.clicked.connect(lambda: self.subtitle_edit.clear())
        subtitle_file_layout.addWidget(self.subtitle_edit)
        subtitle_file_layout.addWidget(self.subtitle_btn)
        subtitle_file_layout.addWidget(self.subtitle_clear_btn)
        
        subtitle_layout.addLayout(subtitle_file_layout)
        subtitle_group.setLayout(subtitle_layout)
        
        # 配音文件
        voice_group = QGroupBox("配音/声音 (可选)")
        voice_layout = QVBoxLayout()
        
        voice_file_layout = QHBoxLayout()
        voice_file_layout.addWidget(QLabel("配音文件:"))
        self.voice_edit = QLineEdit()
        self.voice_edit.setPlaceholderText("选择配音文件，留空则保留原声...")
        self.voice_btn = QPushButton("浏览")
        self.voice_btn.clicked.connect(self.browse_voice)
        self.voice_clear_btn = QPushButton("清除")
        self.voice_clear_btn.clicked.connect(lambda: self.voice_edit.clear())
        voice_file_layout.addWidget(self.voice_edit)
        voice_file_layout.addWidget(self.voice_btn)
        voice_file_layout.addWidget(self.voice_clear_btn)
        
        # 智能选择配音
        voice_auto_layout = QHBoxLayout()
        voice_auto_layout.addWidget(QLabel("快速选择:"))
        self.voice_auto_btn = QPushButton("自动匹配中文配音")
        self.voice_auto_btn.setToolTip("根据字幕文件自动查找对应的中文配音")
        self.voice_auto_btn.clicked.connect(self.auto_select_voice)
        voice_auto_layout.addWidget(self.voice_auto_btn)
        voice_auto_layout.addStretch()
        
        voice_vol_layout = QHBoxLayout()
        voice_vol_layout.addWidget(QLabel("音量:"))
        self.voice_volume = QDoubleSpinBox()
        self.voice_volume.setRange(0.0, 2.0)
        self.voice_volume.setSingleStep(0.1)
        self.voice_volume.setValue(1.0)
        voice_vol_layout.addWidget(self.voice_volume)
        voice_vol_layout.addStretch()
        
        voice_layout.addLayout(voice_file_layout)
        voice_layout.addLayout(voice_auto_layout)
        voice_layout.addLayout(voice_vol_layout)
        voice_group.setLayout(voice_layout)
        
        # 输出设置
        output_group = QGroupBox("输出设置")
        output_layout = QHBoxLayout()
        self.output_edit = QLineEdit()
        self.output_edit.setPlaceholderText("输出文件路径 (默认: 原文件名_处理完成.mp4)")
        self.output_btn = QPushButton("浏览")
        self.output_btn.clicked.connect(self.browse_output)
        output_layout.addWidget(self.output_edit)
        output_layout.addWidget(self.output_btn)
        output_group.setLayout(output_layout)
        
        # 执行按钮
        self.compose_btn = QPushButton("开始合成")
        self.compose_btn.clicked.connect(self.start_compose)
        self.compose_btn.setMinimumHeight(40)
        
        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(False)
        
        # 添加到主布局
        layout.addWidget(video_group)
        layout.addWidget(bgm_group)
        layout.addWidget(subtitle_group)
        layout.addWidget(voice_group)
        layout.addWidget(output_group)
        layout.addWidget(self.compose_btn)
        layout.addWidget(self.progress_bar)
        layout.addStretch()
    
    def browse_video(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择视频文件", "",
            "视频文件 (*.mp4 *.avi *.mkv *.mov *.webm);;所有文件 (*.*)"
        )
        if file_path:
            self.video_edit.setText(file_path)
            # 自动设置输出路径
            if not self.output_edit.text():
                base_name = os.path.splitext(file_path)[0]
                self.output_edit.setText(f"{base_name}_处理完成.mp4")
    
    def browse_bgm(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择背景音乐", "",
            "音频文件 (*.mp3 *.wav *.aac *.flac *.ogg);;所有文件 (*.*)"
        )
        if file_path:
            self.bgm_edit.setText(file_path)
    
    def browse_subtitle(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择字幕文件", "",
            "字幕文件 (*.srt *.ass *.ssa *.vtt);;所有文件 (*.*)"
        )
        if file_path:
            self.subtitle_edit.setText(file_path)
    
    def auto_select_voice(self):
        """自动匹配中文配音文件"""
        subtitle_path = self.subtitle_edit.text().strip()
        if not subtitle_path:
            self.log("请先选择字幕文件")
            return
        
        # 尝试查找对应的中文配音
        base_path = os.path.splitext(subtitle_path)[0]
        
        # 移除可能的语言后缀
        for suffix in ["_中文", "_英文", "_双语", "_en", "_zh"]:
            if base_path.endswith(suffix):
                base_path = base_path[:-len(suffix)]
                break
        
        # 尝试多个可能的配音文件名
        possible_names = [
            f"{base_path}_中文.mp3",
            f"{base_path}_中文.wav",
            f"{base_path}_zh.mp3",
            f"{base_path}_chinese.mp3",
        ]
        
        for voice_file in possible_names:
            if os.path.exists(voice_file):
                self.voice_edit.setText(voice_file)
                self.log(f"✓ 自动匹配到配音: {os.path.basename(voice_file)}")
                return
        
        self.log("未找到匹配的中文配音文件")
        self.log(f"提示: 配音文件应命名为 {os.path.basename(base_path)}_中文.mp3")
    
    def browse_voice(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择配音文件", "",
            "音频文件 (*.mp3 *.wav *.aac *.flac *.ogg);;所有文件 (*.*)"
        )
        if file_path:
            self.voice_edit.setText(file_path)
    
    def browse_output(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self, "保存视频", "",
            "MP4 视频 (*.mp4);;所有文件 (*.*)"
        )
        if file_path:
            self.output_edit.setText(file_path)
    
    def start_compose(self):
        video_path = self.video_edit.text().strip()
        
        if not video_path:
            self.log("请选择视频文件")
            return
        
        if not os.path.exists(video_path):
            self.log("视频文件不存在")
            return
        
        # 获取输出路径
        output_path = self.output_edit.text().strip()
        if not output_path:
            base_name = os.path.splitext(video_path)[0]
            output_path = f"{base_name}_处理完成.mp4"
            self.output_edit.setText(output_path)
        
        self.compose_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.log("=" * 40)
        self.log("开始视频合成...")
        
        ffmpeg_path = self.get_ffmpeg_path()
        
        self.thread = ComposerThread(
            video_path=video_path,
            output_path=output_path,
            bgm_path=self.bgm_edit.text().strip(),
            subtitle_path=self.subtitle_edit.text().strip(),
            voice_path=self.voice_edit.text().strip(),
            bgm_volume=self.bgm_volume.value(),
            voice_volume=self.voice_volume.value(),
            ffmpeg_path=ffmpeg_path
        )
        self.thread.progress.connect(self.log)
        self.thread.finished.connect(self.on_finished)
        self.thread.start()
    
    def on_finished(self, success, message):
        self.progress_bar.setVisible(False)
        if success:
            console_info(message, "视频合成")
        else:
            console_error(message, "视频合成")
        self.compose_btn.setEnabled(True)
    
    def log(self, message):
        console_info(message, "视频合成")
    
    def get_ffmpeg_path(self):
        import json
        try:
            with open("config.json", "r") as f:
                config = json.load(f)
                return config.get("ffmpeg_path", "ffmpeg")
        except:
            return "ffmpeg"
