from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QLineEdit, QPushButton, QFileDialog, 
                             QGroupBox, QSpinBox, QComboBox, QProgressBar)
from PyQt6.QtCore import QThread, pyqtSignal
from .console_widget import console_info, console_error
import os


class TranscoderThread(QThread):
    finished = pyqtSignal(bool, str)
    
    def __init__(self, input_path, output_path, crf, preset, ffmpeg_path):
        super().__init__()
        self.input_path = input_path
        self.output_path = output_path
        self.crf = crf
        self.preset = preset
        self.ffmpeg_path = ffmpeg_path
    
    def run(self):
        try:
            from video_tool.core.transcoder import Transcoder
            transcoder = Transcoder(self.ffmpeg_path)
            transcoder.transcode(self.input_path, self.output_path, self.crf, self.preset)
            self.finished.emit(True, "转码完成！")
        except Exception as e:
            self.finished.emit(False, f"错误: {str(e)}")


class TranscoderWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()
        self.thread = None
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # 输入文件
        input_group = QGroupBox("输入视频")
        input_layout = QHBoxLayout()
        self.input_edit = QLineEdit()
        self.input_edit.setPlaceholderText("选择视频文件...")
        self.browse_input_btn = QPushButton("浏览")
        self.browse_input_btn.clicked.connect(self.browse_input)
        input_layout.addWidget(self.input_edit)
        input_layout.addWidget(self.browse_input_btn)
        input_group.setLayout(input_layout)
        
        # 输出设置
        output_group = QGroupBox("输出设置")
        output_layout = QVBoxLayout()
        
        output_file_layout = QHBoxLayout()
        self.output_edit = QLineEdit()
        self.output_edit.setPlaceholderText("选择输出路径...")
        self.browse_output_btn = QPushButton("浏览")
        self.browse_output_btn.clicked.connect(self.browse_output)
        output_file_layout.addWidget(self.output_edit)
        output_file_layout.addWidget(self.browse_output_btn)
        
        # CRF 设置
        crf_layout = QHBoxLayout()
        crf_layout.addWidget(QLabel("质量 (CRF):"))
        self.crf_spin = QSpinBox()
        self.crf_spin.setRange(0, 51)
        self.crf_spin.setValue(23)
        crf_layout.addWidget(self.crf_spin)
        crf_layout.addWidget(QLabel("(0=最佳, 51=最差, 推荐18-28)"))
        crf_layout.addStretch()
        
        # Preset 设置
        preset_layout = QHBoxLayout()
        preset_layout.addWidget(QLabel("编码速度:"))
        self.preset_combo = QComboBox()
        self.preset_combo.addItems([
            "ultrafast", "superfast", "veryfast", 
            "faster", "fast", "medium", 
            "slow", "slower", "veryslow"
        ])
        self.preset_combo.setCurrentText("medium")
        preset_layout.addWidget(self.preset_combo)
        preset_layout.addWidget(QLabel("(faster=快但大, slower=慢但小)"))
        preset_layout.addStretch()
        
        output_layout.addLayout(output_file_layout)
        output_layout.addLayout(crf_layout)
        output_layout.addLayout(preset_layout)
        output_group.setLayout(output_layout)
        
        # 执行按钮
        self.transcode_btn = QPushButton("开始转码")
        self.transcode_btn.clicked.connect(self.transcode_video)
        
        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(False)
        
        # 添加到主布局
        layout.addWidget(input_group)
        layout.addWidget(output_group)
        layout.addWidget(self.transcode_btn)
        layout.addWidget(self.progress_bar)
        layout.addStretch()
    
    def browse_input(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择视频文件", "", 
            "视频文件 (*.mp4 *.avi *.mkv *.mov *.flv);;所有文件 (*.*)"
        )
        if file_path:
            self.input_edit.setText(file_path)
            if not self.output_edit.text():
                base_name = os.path.splitext(file_path)[0]
                self.output_edit.setText(f"{base_name}_transcoded.mp4")
    
    def browse_output(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self, "保存视频文件", "", 
            "视频文件 (*.mp4);;所有文件 (*.*)"
        )
        if file_path:
            self.output_edit.setText(file_path)
    
    def transcode_video(self):
        input_path = self.input_edit.text()
        output_path = self.output_edit.text()
        
        if not input_path or not output_path:
            self.log("请选择输入和输出文件")
            return
        
        if not os.path.exists(input_path):
            self.log("输入文件不存在")
            return
        
        self.transcode_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.log("开始转码...")
        
        ffmpeg_path = self.get_ffmpeg_path()
        
        self.thread = TranscoderThread(
            input_path, output_path,
            self.crf_spin.value(),
            self.preset_combo.currentText(),
            ffmpeg_path
        )
        self.thread.finished.connect(self.on_transcode_finished)
        self.thread.start()
    
    def on_transcode_finished(self, success, message):
        self.progress_bar.setVisible(False)
        if success:
            console_info(message, "视频转码")
        else:
            console_error(message, "视频转码")
        self.transcode_btn.setEnabled(True)
    
    def log(self, message):
        console_info(message, "视频转码")
    
    def get_ffmpeg_path(self):
        from video_tool.utils import get_ffmpeg_path
        return get_ffmpeg_path()
