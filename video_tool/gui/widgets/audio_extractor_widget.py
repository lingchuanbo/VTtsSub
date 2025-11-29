from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QLineEdit, QPushButton, QFileDialog, QComboBox,
                             QGroupBox, QCheckBox, QRadioButton,
                             QButtonGroup, QProgressBar)
from PyQt6.QtCore import QThread, pyqtSignal
from .console_widget import console_info, console_error
import os


class ExtractorThread(QThread):
    """简单音频提取线程"""
    finished = pyqtSignal(bool, str)
    progress = pyqtSignal(str)
    
    def __init__(self, video_path, output_path, format_type, ffmpeg_path):
        super().__init__()
        self.video_path = video_path
        self.output_path = output_path
        self.format_type = format_type
        self.ffmpeg_path = ffmpeg_path
    
    def run(self):
        try:
            from video_tool.core.audio_extractor import AudioExtractor
            extractor = AudioExtractor(self.ffmpeg_path)
            extractor.extract_audio(self.video_path, self.output_path, self.format_type)
            self.finished.emit(True, "音频提取成功！")
        except Exception as e:
            self.finished.emit(False, f"错误: {str(e)}")


class DemucsThread(QThread):
    """Demucs 人声分离线程"""
    finished = pyqtSignal(bool, str)
    progress = pyqtSignal(str)
    
    def __init__(self, video_path, output_dir, ffmpeg_path, model, device, 
                 output_vocals=True, output_accompaniment=True, output_silent_video=True):
        super().__init__()
        self.video_path = video_path
        self.output_dir = output_dir
        self.ffmpeg_path = ffmpeg_path
        self.model = model
        self.device = device
        self.output_vocals = output_vocals
        self.output_accompaniment = output_accompaniment
        self.output_silent_video = output_silent_video
    
    def run(self):
        try:
            from video_tool.core.audio_extractor import FullVideoProcessor
            
            processor = FullVideoProcessor(
                ffmpeg_path=self.ffmpeg_path,
                demucs_model=self.model,
                device=self.device
            )
            
            results = processor.process(
                self.video_path, 
                self.output_dir,
                progress_callback=lambda msg: self.progress.emit(msg),
                output_vocals=self.output_vocals,
                output_accompaniment=self.output_accompaniment,
                output_silent_video=self.output_silent_video
            )
            
            self.finished.emit(True, "处理完成！")
        except Exception as e:
            import traceback
            self.finished.emit(False, f"错误: {str(e)}\n{traceback.format_exc()}")


class AudioExtractorWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()
        self.thread = None
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # 输入文件组
        input_group = QGroupBox("输入视频")
        input_layout = QHBoxLayout()
        self.input_edit = QLineEdit()
        self.input_edit.setPlaceholderText("选择视频文件...")
        self.browse_input_btn = QPushButton("浏览")
        self.browse_input_btn.clicked.connect(self.browse_input)
        input_layout.addWidget(self.input_edit)
        input_layout.addWidget(self.browse_input_btn)
        input_group.setLayout(input_layout)
        
        # 处理模式选择
        mode_group = QGroupBox("处理模式")
        mode_layout = QVBoxLayout()
        
        self.mode_group = QButtonGroup(self)
        self.simple_mode = QRadioButton("简单提取 - 仅提取音频")
        self.demucs_mode = QRadioButton("Demucs 分离 - 分离人声/伴奏 + 无声视频")
        self.demucs_mode.setChecked(True)
        
        self.mode_group.addButton(self.simple_mode, 0)
        self.mode_group.addButton(self.demucs_mode, 1)
        
        self.simple_mode.toggled.connect(self.on_mode_changed)
        
        mode_layout.addWidget(self.simple_mode)
        mode_layout.addWidget(self.demucs_mode)
        mode_group.setLayout(mode_layout)
        
        # 简单提取选项
        self.simple_options = QGroupBox("简单提取选项")
        simple_layout = QVBoxLayout()
        
        output_file_layout = QHBoxLayout()
        output_file_layout.addWidget(QLabel("输出文件:"))
        self.output_edit = QLineEdit()
        self.output_edit.setPlaceholderText("选择输出路径...")
        self.browse_output_btn = QPushButton("浏览")
        self.browse_output_btn.clicked.connect(self.browse_output)
        output_file_layout.addWidget(self.output_edit)
        output_file_layout.addWidget(self.browse_output_btn)
        
        format_layout = QHBoxLayout()
        format_layout.addWidget(QLabel("音频格式:"))
        self.format_combo = QComboBox()
        self.format_combo.addItems(["mp3", "wav", "aac"])
        format_layout.addWidget(self.format_combo)
        format_layout.addStretch()
        
        simple_layout.addLayout(output_file_layout)
        simple_layout.addLayout(format_layout)
        self.simple_options.setLayout(simple_layout)
        
        # Demucs 选项
        self.demucs_options = QGroupBox("Demucs 分离选项")
        demucs_layout = QVBoxLayout()
        
        # 输出目录
        output_dir_layout = QHBoxLayout()
        output_dir_layout.addWidget(QLabel("输出目录:"))
        self.output_dir_edit = QLineEdit()
        self.output_dir_edit.setPlaceholderText("选择输出目录...")
        self.browse_output_dir_btn = QPushButton("浏览")
        self.browse_output_dir_btn.clicked.connect(self.browse_output_dir)
        output_dir_layout.addWidget(self.output_dir_edit)
        output_dir_layout.addWidget(self.browse_output_dir_btn)
        
        # 输出选项 (复选框)
        output_options_layout = QHBoxLayout()
        output_options_layout.addWidget(QLabel("输出内容:"))
        self.vocals_checkbox = QCheckBox("人声")
        self.vocals_checkbox.setChecked(True)
        self.accompaniment_checkbox = QCheckBox("伴奏")
        self.accompaniment_checkbox.setChecked(True)
        self.silent_video_checkbox = QCheckBox("无声视频")
        self.silent_video_checkbox.setChecked(True)
        output_options_layout.addWidget(self.vocals_checkbox)
        output_options_layout.addWidget(self.accompaniment_checkbox)
        output_options_layout.addWidget(self.silent_video_checkbox)
        output_options_layout.addStretch()
        
        # 模型选择
        model_layout = QHBoxLayout()
        model_layout.addWidget(QLabel("Demucs 模型:"))
        self.model_combo = QComboBox()
        self.model_combo.addItems([
            "htdemucs",      # 默认混合模型
            "htdemucs_ft",   # 微调版本，质量更高
            "htdemucs_6s",   # 6源分离
            "mdx_extra",     # MDX 模型
            "mdx_extra_q",   # MDX 量化版
        ])
        self.model_combo.setCurrentText("htdemucs")
        model_layout.addWidget(self.model_combo)
        model_layout.addStretch()
        
        # 设备选择
        device_layout = QHBoxLayout()
        device_layout.addWidget(QLabel("处理设备:"))
        self.device_combo = QComboBox()
        self.device_combo.addItems(["cuda", "cpu"])
        device_layout.addWidget(self.device_combo)
        device_layout.addStretch()
        
        # 输出说明
        info_label = QLabel(
            "输出文件命名规则：\n"
            "  • 人声: 文件名_vocals.wav\n"
            "  • 伴奏: 文件名_accompaniment.wav\n"
            "  • 无声视频: 文件名_silent.mp4\n"
            "  • 其他分离源: 文件名_drums.wav, 文件名_bass.wav 等"
        )
        info_label.setStyleSheet("color: gray; font-size: 11px;")
        
        demucs_layout.addLayout(output_dir_layout)
        demucs_layout.addLayout(output_options_layout)
        demucs_layout.addLayout(model_layout)
        demucs_layout.addLayout(device_layout)
        demucs_layout.addWidget(info_label)
        self.demucs_options.setLayout(demucs_layout)
        self.demucs_options.setVisible(False)
        
        # 执行按钮
        self.extract_btn = QPushButton("开始处理")
        self.extract_btn.clicked.connect(self.start_process)
        
        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # 不确定进度模式
        self.progress_bar.setVisible(False)
        
        # 添加到主布局
        layout.addWidget(input_group)
        layout.addWidget(mode_group)
        layout.addWidget(self.simple_options)
        layout.addWidget(self.demucs_options)
        layout.addWidget(self.extract_btn)
        layout.addWidget(self.progress_bar)
        layout.addStretch()
    
    def on_mode_changed(self, checked):
        """切换处理模式"""
        is_simple = self.simple_mode.isChecked()
        self.simple_options.setVisible(is_simple)
        self.demucs_options.setVisible(not is_simple)
    
    def browse_input(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择视频文件", "", 
            "视频文件 (*.mp4 *.avi *.mkv *.mov *.flv *.webm);;所有文件 (*.*)"
        )
        if file_path:
            self.input_edit.setText(file_path)
            # 自动设置输出路径
            base_name = os.path.splitext(file_path)[0]
            base_dir = os.path.dirname(file_path)
            
            if not self.output_edit.text():
                self.output_edit.setText(f"{base_name}.{self.format_combo.currentText()}")
            
            if not self.output_dir_edit.text():
                self.output_dir_edit.setText(base_dir)
    
    def browse_output(self):
        format_type = self.format_combo.currentText()
        file_path, _ = QFileDialog.getSaveFileName(
            self, "保存音频文件", "", 
            f"音频文件 (*.{format_type});;所有文件 (*.*)"
        )
        if file_path:
            self.output_edit.setText(file_path)
    
    def browse_output_dir(self):
        dir_path = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if dir_path:
            self.output_dir_edit.setText(dir_path)
    
    def start_process(self):
        """开始处理"""
        video_path = self.input_edit.text()
        
        if not video_path:
            self.log("请选择输入视频文件")
            return
        
        if not os.path.exists(video_path):
            self.log("输入文件不存在")
            return
        
        ffmpeg_path = self.get_ffmpeg_path()
        
        if self.simple_mode.isChecked():
            self.start_simple_extract(video_path, ffmpeg_path)
        else:
            self.start_demucs_process(video_path, ffmpeg_path)
    
    def start_simple_extract(self, video_path, ffmpeg_path):
        """简单音频提取"""
        output_path = self.output_edit.text()
        
        if not output_path:
            self.log("请选择输出文件路径")
            return
        
        self.extract_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.log("开始提取音频...")
        
        self.thread = ExtractorThread(
            video_path, output_path, 
            self.format_combo.currentText(),
            ffmpeg_path
        )
        self.thread.finished.connect(self.on_finished)
        self.thread.start()
    
    def start_demucs_process(self, video_path, ffmpeg_path):
        """Demucs 人声分离处理"""
        output_dir = self.output_dir_edit.text()
        
        if not output_dir:
            self.log("请选择输出目录")
            return
        
        # 获取输出选项
        output_vocals = self.vocals_checkbox.isChecked()
        output_accompaniment = self.accompaniment_checkbox.isChecked()
        output_silent_video = self.silent_video_checkbox.isChecked()
        
        if not output_vocals and not output_accompaniment and not output_silent_video:
            self.log("请至少选择一个输出内容")
            return
        
        self.extract_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.log("=" * 40)
        self.log("开始 Demucs 人声分离处理...")
        self.log(f"模型: {self.model_combo.currentText()}")
        self.log(f"设备: {self.device_combo.currentText()}")
        outputs = []
        if output_vocals:
            outputs.append("人声")
        if output_accompaniment:
            outputs.append("伴奏")
        if output_silent_video:
            outputs.append("无声视频")
        self.log(f"输出内容: {', '.join(outputs)}")
        self.log("=" * 40)
        
        self.thread = DemucsThread(
            video_path,
            output_dir,
            ffmpeg_path,
            self.model_combo.currentText(),
            self.device_combo.currentText(),
            output_vocals=output_vocals,
            output_accompaniment=output_accompaniment,
            output_silent_video=output_silent_video
        )
        self.thread.progress.connect(self.log)
        self.thread.finished.connect(self.on_finished)
        self.thread.start()
    
    def on_finished(self, success, message):
        self.progress_bar.setVisible(False)
        if success:
            console_info(message, "音频提取")
        else:
            console_error(message, "音频提取")
        self.extract_btn.setEnabled(True)
    
    def log(self, message):
        console_info(message, "音频提取")
    
    def get_ffmpeg_path(self):
        import json
        try:
            with open("config.json", "r") as f:
                config = json.load(f)
                return config.get("ffmpeg_path", "ffmpeg")
        except:
            return "ffmpeg"
