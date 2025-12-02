from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QLineEdit, QPushButton, QFileDialog, QComboBox,
                             QGroupBox, QProgressBar, QRadioButton, 
                             QButtonGroup, QCheckBox, QSpinBox, QDoubleSpinBox)
from PyQt6.QtCore import QThread, pyqtSignal, Qt
from .console_widget import console_info, console_error, console_warning
import os


class ASRThread(QThread):
    finished = pyqtSignal(bool, str)
    progress = pyqtSignal(str)
    
    def __init__(self, audio_path, output_path, model_size, engine_type, api_key=None, 
                 language_code=None, diarize=False, api_url=None,
                 pause_threshold=0.5, max_words_per_segment=12,
                 use_vad=True, vad_threshold=0.5):
        super().__init__()
        self.audio_path = audio_path
        self.output_path = output_path
        self.model_size = model_size
        self.engine_type = engine_type
        self.api_key = api_key
        self.language_code = language_code
        self.diarize = diarize
        self.api_url = api_url
        self.pause_threshold = pause_threshold
        self.max_words_per_segment = max_words_per_segment
        # VAD 参数
        self.use_vad = use_vad
        self.vad_threshold = vad_threshold
    
    def run(self):
        try:
            from video_tool.core.asr_processor import ASRProcessor
            self.progress.emit(f"初始化 ASR 处理器 ({self.engine_type.upper()})...")
            processor = ASRProcessor(
                model_size=self.model_size,
                engine_type=self.engine_type,
                api_key=self.api_key,
                api_url=self.api_url
            )
            # 设置断句参数
            processor.pause_threshold = self.pause_threshold
            processor.max_words_per_segment = self.max_words_per_segment
            # 设置 VAD 参数
            processor.use_vad = self.use_vad
            processor.vad_threshold = self.vad_threshold
            
            vad_info = f", VAD: {'启用' if self.use_vad else '禁用'}" if self.engine_type == "whisper" else ""
            self.progress.emit(f"开始转录... (停顿阈值: {self.pause_threshold}s, 每段最大词数: {self.max_words_per_segment}{vad_info})")
            
            # 获取转录结果
            segments = processor.transcribe(
                self.audio_path, 
                output_srt_path=None,
                language_code=self.language_code,
                diarize=self.diarize
            )
            
            # 保存结果
            processor._save_as_srt(segments, self.output_path)
            
            self.finished.emit(True, f"字幕生成成功！保存至: {self.output_path}")
        except Exception as e:
            self.finished.emit(False, f"错误: {str(e)}")


class ASRWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()
        self.thread = None
        self.load_api_key_from_config()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # 输入文件组
        input_group = QGroupBox("输入音频")
        input_layout = QVBoxLayout()
        
        # 本地文件输入
        file_layout = QHBoxLayout()
        self.input_edit = QLineEdit()
        self.input_edit.setPlaceholderText("选择音频文件...")
        self.browse_input_btn = QPushButton("浏览")
        self.browse_input_btn.clicked.connect(self.browse_input)
        file_layout.addWidget(QLabel("本地文件:"))
        file_layout.addWidget(self.input_edit)
        file_layout.addWidget(self.browse_input_btn)
        
        # 隐藏的 URL 输入（保持兼容性）
        self.url_input_edit = QLineEdit()
        self.url_input_edit.hide()
        self.qwen_hint_label = QLabel()
        self.qwen_hint_label.hide()
        
        input_layout.addLayout(file_layout)
        input_group.setLayout(input_layout)
        
        # ASR 引擎选择
        engine_group = QGroupBox("ASR 引擎")
        engine_layout = QVBoxLayout()
        
        # 引擎信息显示
        engine_info_layout = QHBoxLayout()
        engine_info_layout.addWidget(QLabel("引擎:"))
        self.engine_label = QLabel("Faster-Whisper (本地, GPU加速)")
        self.engine_label.setStyleSheet("font-weight: bold; color: #4A90E2;")
        engine_info_layout.addWidget(self.engine_label)
        engine_info_layout.addStretch()
        
        # 隐藏的引擎选择（保持兼容性）
        self.engine_combo = QComboBox()
        self.engine_combo.addItems(["Faster-Whisper (本地, 更快)"])
        self.engine_combo.hide()
        
        # 隐藏的 API 相关控件（保持兼容性）
        self.api_key_edit = QLineEdit()
        self.api_key_edit.hide()
        self.api_url_edit = QLineEdit()
        self.api_url_edit.hide()
        
        engine_layout.addLayout(engine_info_layout)
        engine_group.setLayout(engine_layout)
        
        # 输出文件组
        output_group = QGroupBox("输出设置")
        output_layout = QVBoxLayout()
        
        output_file_layout = QHBoxLayout()
        self.output_edit = QLineEdit()
        self.output_edit.setPlaceholderText("选择输出路径...")
        self.browse_output_btn = QPushButton("浏览")
        self.browse_output_btn.clicked.connect(self.browse_output)
        output_file_layout.addWidget(self.output_edit)
        output_file_layout.addWidget(self.browse_output_btn)
        
        # 模型选择
        model_layout = QHBoxLayout()
        model_layout.addWidget(QLabel("模型:"))
        self.model_combo = QComboBox()
        self.model_combo.addItems([
            "tiny",
            "base", 
            "small",
            "medium",
            "large-v2",
            "large-v3",
            "large-v3-turbo",
            "distil-large-v2",
            "distil-large-v3"
        ])
        self.model_combo.setCurrentText("large-v3-turbo")
        model_layout.addWidget(self.model_combo)
        self.model_hint_label = QLabel("(推荐 large-v3-turbo: 速度快+质量高)")
        self.model_hint_label.setStyleSheet("color: gray; font-size: 10px;")
        model_layout.addWidget(self.model_hint_label)
        model_layout.addStretch()
        
        # 语言选择
        lang_layout = QHBoxLayout()
        lang_layout.addWidget(QLabel("语言:"))
        self.lang_combo = QComboBox()
        self.lang_combo.addItems([
            "自动检测",
            "en - 英语",
            "zh - 中文",
            "ja - 日语",
            "ko - 韩语",
            "es - 西班牙语",
            "fr - 法语",
            "de - 德语",
            "ru - 俄语",
            "pt - 葡萄牙语",
            "it - 意大利语"
        ])
        self.lang_combo.setEnabled(True)
        lang_layout.addWidget(self.lang_combo)
        
        # 隐藏的说话人识别（保持兼容性）
        self.diarize_check = QCheckBox()
        self.diarize_check.hide()
        lang_layout.addStretch()
        
        # 断句设置（Whisper）- 暂时隐藏，使用后处理自动优化
        # segment_layout = QHBoxLayout()
        # segment_layout.addWidget(QLabel("断句设置:"))
        # 
        # segment_layout.addWidget(QLabel("停顿阈值:"))
        # self.pause_threshold_spin = QDoubleSpinBox()
        # self.pause_threshold_spin.setRange(0.1, 3.0)
        # self.pause_threshold_spin.setSingleStep(0.1)
        # self.pause_threshold_spin.setValue(0.5)
        # self.pause_threshold_spin.setDecimals(1)
        # self.pause_threshold_spin.setSuffix(" 秒")
        # self.pause_threshold_spin.setToolTip("超过此时间的停顿会分成新段落")
        # segment_layout.addWidget(self.pause_threshold_spin)
        # 
        # segment_layout.addWidget(QLabel("每段最大词数:"))
        # self.max_words_spin = QSpinBox()
        # self.max_words_spin.setRange(5, 50)
        # self.max_words_spin.setValue(12)
        # self.max_words_spin.setToolTip("每个字幕段落的最大词数")
        # segment_layout.addWidget(self.max_words_spin)
        # 
        # segment_layout.addStretch()
        
        # 使用默认值
        self.pause_threshold_spin = None
        self.max_words_spin = None
        
        # VAD 设置（Whisper 专用）
        vad_layout = QHBoxLayout()
        self.vad_check = QCheckBox("启用 Silero-VAD")
        self.vad_check.setChecked(True)
        self.vad_check.setToolTip("使用 Silero-VAD 提升时间戳精准度，减少幻觉和循环错误")
        self.vad_check.stateChanged.connect(self.on_vad_changed)
        vad_layout.addWidget(self.vad_check)
        
        vad_layout.addWidget(QLabel("VAD 阈值:"))
        self.vad_threshold_spin = QDoubleSpinBox()
        self.vad_threshold_spin.setRange(0.1, 0.9)
        self.vad_threshold_spin.setSingleStep(0.1)
        self.vad_threshold_spin.setValue(0.5)
        self.vad_threshold_spin.setDecimals(1)
        self.vad_threshold_spin.setToolTip("VAD 检测阈值 (0.1-0.9)\n越高越严格，可能漏检轻声\n越低越宽松，可能误检噪音")
        vad_layout.addWidget(self.vad_threshold_spin)
        
        self.vad_hint_label = QLabel("(推荐 0.5，嘈杂环境可调高)")
        self.vad_hint_label.setStyleSheet("color: gray; font-size: 10px;")
        vad_layout.addWidget(self.vad_hint_label)
        vad_layout.addStretch()
        
        output_layout.addLayout(output_file_layout)
        output_layout.addLayout(model_layout)
        output_layout.addLayout(lang_layout)
        # output_layout.addLayout(segment_layout)  # 断句设置暂时隐藏
        output_layout.addLayout(vad_layout)
        output_group.setLayout(output_layout)
        
        # 执行按钮
        button_layout = QHBoxLayout()
        self.process_btn = QPushButton("开始识别")
        self.process_btn.clicked.connect(self.process_asr)
        self.save_settings_btn = QPushButton("保存设置")
        self.save_settings_btn.clicked.connect(self.save_settings_manually)
        button_layout.addWidget(self.process_btn)
        button_layout.addWidget(self.save_settings_btn)
        button_layout.addStretch()
        
        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # 不确定进度
        self.progress_bar.hide()
        
        # 添加到主布局
        layout.addWidget(input_group)
        layout.addWidget(engine_group)
        layout.addWidget(output_group)
        layout.addLayout(button_layout)
        layout.addWidget(self.progress_bar)
        layout.addStretch()
    
    def on_engine_changed(self):
        """当 ASR 引擎切换时更新界面 - 简化版，只支持 Faster-Whisper"""
        # 固定使用 Faster-Whisper
        self.vad_check.setEnabled(True)
        self.vad_threshold_spin.setEnabled(self.vad_check.isChecked())
        self.vad_hint_label.setVisible(True)
        self.lang_combo.setEnabled(True)
    
    def load_api_key_from_config(self):
        """从配置文件加载设置"""
        import json
        try:
            with open("config.json", "r") as f:
                config = json.load(f)
                
                # 加载 ASR 设置
                asr_config = config.get("asr_settings", {})
                
                # 恢复模型选择
                model = asr_config.get("model", "large-v3-turbo")
                model_index = self.model_combo.findText(model)
                if model_index >= 0:
                    self.model_combo.setCurrentIndex(model_index)
                
                # 恢复语言选择
                language = asr_config.get("language", "自动检测")
                lang_index = self.lang_combo.findText(language)
                if lang_index >= 0:
                    self.lang_combo.setCurrentIndex(lang_index)
                
                # 恢复 VAD 设置
                use_vad = asr_config.get("use_vad", True)
                self.vad_check.setChecked(use_vad)
                
                vad_threshold = asr_config.get("vad_threshold", 0.5)
                self.vad_threshold_spin.setValue(vad_threshold)
                
        except Exception as e:
            print(f"加载配置失败: {e}")
    
    def save_api_key_to_config(self):
        """保存设置到配置文件"""
        import json
        api_key = self.api_key_edit.text().strip()
        
        try:
            # 读取现有配置
            config = {}
            try:
                with open("config.json", "r") as f:
                    config = json.load(f)
            except:
                pass
            
            # 保存 ASR 设置
            config["asr_settings"] = {
                "engine": "faster-whisper",
                "model": self.model_combo.currentText(),
                "language": self.lang_combo.currentText(),
                "use_vad": self.vad_check.isChecked(),
                "vad_threshold": self.vad_threshold_spin.value()
            }
            
            # 保存配置
            with open("config.json", "w") as f:
                json.dump(config, f, indent=4)
            
            self.log("设置已自动保存到配置文件")
        except Exception as e:
            self.log(f"保存设置失败: {str(e)}")
    
    def save_settings_manually(self):
        """手动保存设置（通过按钮触发）"""
        self.save_api_key_to_config()
        self.log("配置已手动保存")
    
    def refresh_models(self):
        """刷新模型列表"""
        self.log("Faster-Whisper 模型列表已是最新")
    
    def browse_input(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择音频文件", "", 
            "音频文件 (*.mp3 *.wav *.m4a *.aac);;所有文件 (*.*)"
        )
        if file_path:
            self.input_edit.setText(file_path)
            if not self.output_edit.text():
                base_name = os.path.splitext(file_path)[0]
                # 清理文件名中的 _vocals 后缀
                if base_name.endswith('_vocals'):
                    base_name = base_name[:-7]
                self.output_edit.setText(f"{base_name}.srt")
    
    def browse_output(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self, "保存字幕文件", "", 
            "字幕文件 (*.srt);;所有文件 (*.*)"
        )
        if file_path:
            self.output_edit.setText(file_path)
    
    def process_asr(self):
        audio_path = self.input_edit.text()
        output_path = self.output_edit.text()
        
        # 验证输入
        if not audio_path or not output_path:
            self.log("请选择输入和输出文件")
            return
        
        if not os.path.exists(audio_path):
            self.log("输入文件不存在")
            return
        
        # 固定使用 Faster-Whisper
        engine_type = "faster-whisper"
        
        # 获取语言代码
        language_code = None
        lang_text = self.lang_combo.currentText()
        if lang_text != "自动检测":
            language_code = lang_text.split(" - ")[0]
        
        self.process_btn.setEnabled(False)
        self.progress_bar.show()
        
        # 获取 VAD 参数
        use_vad = self.vad_check.isChecked()
        vad_threshold = self.vad_threshold_spin.value()
        
        self.log(f"开始语音识别 (使用 Faster-Whisper)...")
        self.log(f"模型: {self.model_combo.currentText()}")
        if use_vad:
            self.log(f"VAD 已启用 (阈值: {vad_threshold})")
        
        self.thread = ASRThread(
            audio_path, output_path, 
            self.model_combo.currentText(),
            engine_type,
            api_key=None,
            language_code=language_code,
            diarize=False,
            api_url=None,
            pause_threshold=0.5,
            max_words_per_segment=20,
            use_vad=use_vad,
            vad_threshold=vad_threshold
        )
        self.thread.finished.connect(self.on_process_finished)
        self.thread.progress.connect(self.log)
        self.thread.start()
    
    def on_process_finished(self, success, message):
        self.log(message)
        self.process_btn.setEnabled(True)
        self.progress_bar.hide()
        
        # 保存配置
        if success:
            self.save_api_key_to_config()
    
    def on_vad_changed(self, state):
        """当 VAD 选项改变时"""
        enabled = state == Qt.CheckState.Checked.value
        self.vad_threshold_spin.setEnabled(enabled)
    
    def log(self, message):
        console_info(message, "语音识别")
