from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QLineEdit, QPushButton, QFileDialog, QGroupBox,
                             QSlider, QDoubleSpinBox, QComboBox,
                             QSpinBox, QCheckBox, QProgressBar, QScrollArea,
                             QFrame)
from PyQt6.QtCore import QThread, pyqtSignal, Qt
from .console_widget import console_info, console_error
import os


class ComposerThread(QThread):
    """视频合成线程"""
    finished = pyqtSignal(bool, str)
    progress = pyqtSignal(str)
    
    def __init__(self, video_path, output_path, bgm_path, subtitle_path, 
                 voice_tracks, bgm_volume, ffmpeg_path):
        super().__init__()
        self.video_path = video_path
        self.output_path = output_path
        self.bgm_path = bgm_path
        self.subtitle_path = subtitle_path
        self.voice_tracks = voice_tracks  # [(path, volume), ...]
        self.bgm_volume = bgm_volume
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
                voice_tracks=self.voice_tracks,
                bgm_volume=self.bgm_volume,
                progress_callback=lambda msg: self.progress.emit(msg)
            )
            
            self.finished.emit(True, "视频合成完成！")
        except Exception as e:
            import traceback
            self.finished.emit(False, f"错误: {str(e)}\n{traceback.format_exc()}")


class VoiceTrackWidget(QFrame):
    """单个音轨控件"""
    removed = pyqtSignal(object)
    
    def __init__(self, track_num=1, parent=None):
        super().__init__(parent)
        self.track_num = track_num
        self.init_ui()
    
    def init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 5, 0, 5)
        
        # 音轨标签
        self.label = QLabel(f"音轨 {self.track_num}:")
        self.label.setFixedWidth(60)
        layout.addWidget(self.label)
        
        # 文件路径
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("选择音频文件...")
        layout.addWidget(self.path_edit)
        
        # 浏览按钮
        self.browse_btn = QPushButton("浏览")
        self.browse_btn.setFixedWidth(60)
        self.browse_btn.clicked.connect(self.browse_file)
        layout.addWidget(self.browse_btn)
        
        # 音量
        layout.addWidget(QLabel("音量:"))
        self.volume_spin = QDoubleSpinBox()
        self.volume_spin.setRange(0.0, 2.0)
        self.volume_spin.setSingleStep(0.1)
        self.volume_spin.setValue(1.0)
        self.volume_spin.setFixedWidth(70)
        layout.addWidget(self.volume_spin)
        
        # 删除按钮
        self.remove_btn = QPushButton("×")
        self.remove_btn.setFixedWidth(30)
        self.remove_btn.setToolTip("删除此音轨")
        self.remove_btn.clicked.connect(lambda: self.removed.emit(self))
        layout.addWidget(self.remove_btn)
    
    def browse_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择音频文件", "",
            "音频文件 (*.mp3 *.wav *.aac *.flac *.ogg);;所有文件 (*.*)"
        )
        if file_path:
            self.path_edit.setText(file_path)
    
    def get_data(self):
        """获取音轨数据 (path, volume)"""
        path = self.path_edit.text().strip()
        if path and os.path.exists(path):
            return (path, self.volume_spin.value())
        return None
    
    def update_label(self, num):
        """更新音轨编号"""
        self.track_num = num
        self.label.setText(f"音轨 {num}:")


class VideoComposerWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.voice_tracks = []  # 存储音轨控件
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
        
        # 配音/声音 - 支持多音轨
        voice_group = QGroupBox("配音/声音 (可选，支持多音轨)")
        voice_layout = QVBoxLayout()
        
        # 音轨容器
        self.voice_container = QWidget()
        self.voice_container_layout = QVBoxLayout(self.voice_container)
        self.voice_container_layout.setContentsMargins(0, 0, 0, 0)
        self.voice_container_layout.setSpacing(5)
        
        # 添加音轨按钮
        add_track_layout = QHBoxLayout()
        self.add_track_btn = QPushButton("+ 添加音轨")
        self.add_track_btn.clicked.connect(self.add_voice_track)
        add_track_layout.addWidget(self.add_track_btn)
        add_track_layout.addStretch()
        
        voice_layout.addWidget(self.voice_container)
        voice_layout.addLayout(add_track_layout)
        voice_group.setLayout(voice_layout)
        
        # 默认添加一个音轨
        self.add_voice_track()
        
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
    
    def add_voice_track(self):
        """添加一个音轨"""
        track_num = len(self.voice_tracks) + 1
        track_widget = VoiceTrackWidget(track_num)
        track_widget.removed.connect(self.remove_voice_track)
        
        self.voice_tracks.append(track_widget)
        self.voice_container_layout.addWidget(track_widget)
        
        # 如果只有一个音轨，隐藏删除按钮
        self.update_remove_buttons()
    
    def remove_voice_track(self, track_widget):
        """删除一个音轨"""
        if track_widget in self.voice_tracks:
            self.voice_tracks.remove(track_widget)
            self.voice_container_layout.removeWidget(track_widget)
            track_widget.deleteLater()
            
            # 更新编号
            for i, track in enumerate(self.voice_tracks):
                track.update_label(i + 1)
            
            self.update_remove_buttons()
    
    def update_remove_buttons(self):
        """更新删除按钮的可见性"""
        # 至少保留一个音轨时，隐藏删除按钮
        show_remove = len(self.voice_tracks) > 1
        for track in self.voice_tracks:
            track.remove_btn.setVisible(show_remove)

    
    def browse_video(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择视频文件", "",
            "视频文件 (*.mp4 *.avi *.mkv *.mov *.webm);;所有文件 (*.*)"
        )
        if file_path:
            self.video_edit.setText(file_path)
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
    
    def browse_output(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self, "保存视频", "",
            "MP4 视频 (*.mp4);;所有文件 (*.*)"
        )
        if file_path:
            self.output_edit.setText(file_path)
    
    def get_voice_tracks(self):
        """获取所有有效的音轨数据"""
        tracks = []
        for track in self.voice_tracks:
            data = track.get_data()
            if data:
                tracks.append(data)
        return tracks
    
    def start_compose(self):
        video_path = self.video_edit.text().strip()
        
        if not video_path:
            self.log("请选择视频文件")
            return
        
        if not os.path.exists(video_path):
            self.log("视频文件不存在")
            return
        
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
        voice_tracks = self.get_voice_tracks()
        
        self.thread = ComposerThread(
            video_path=video_path,
            output_path=output_path,
            bgm_path=self.bgm_edit.text().strip(),
            subtitle_path=self.subtitle_edit.text().strip(),
            voice_tracks=voice_tracks,
            bgm_volume=self.bgm_volume.value(),
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
        from video_tool.utils import get_ffmpeg_path
        return get_ffmpeg_path()
