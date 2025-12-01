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
        
        # URL 输入（仅 Qwen filetrans 需要）
        url_layout = QHBoxLayout()
        self.url_input_edit = QLineEdit()
        self.url_input_edit.setPlaceholderText("仅 filetrans 模型需要公网 URL（如 OSS）")
        self.url_input_edit.setEnabled(False)
        url_layout.addWidget(QLabel("或 URL:"))
        url_layout.addWidget(self.url_input_edit)
        
        # Qwen 提示
        self.qwen_hint_label = QLabel(
            "💡 提示：qwen3-asr-flash 支持本地文件，qwen3-asr-flash-filetrans 需要公网 URL"
        )
        self.qwen_hint_label.setStyleSheet("color: #4A90E2; font-size: 11px;")
        self.qwen_hint_label.setWordWrap(True)
        self.qwen_hint_label.hide()
        
        input_layout.addLayout(file_layout)
        input_layout.addLayout(url_layout)
        input_layout.addWidget(self.qwen_hint_label)
        input_group.setLayout(input_layout)
        
        # ASR 引擎选择
        engine_group = QGroupBox("ASR 引擎")
        engine_layout = QVBoxLayout()
        
        # 引擎选择下拉框
        engine_select_layout = QHBoxLayout()
        engine_select_layout.addWidget(QLabel("选择引擎:"))
        self.engine_combo = QComboBox()
        self.engine_combo.addItems([
            "Whisper (本地, 免费)",
            "ElevenLabs (云端, 需要 API Key)",
            "Qwen ASR (云端, 需要 API Key)"
        ])
        self.engine_combo.currentIndexChanged.connect(self.on_engine_changed)
        engine_select_layout.addWidget(self.engine_combo)
        engine_select_layout.addStretch()
        
        # API Key 输入
        api_key_layout = QHBoxLayout()
        api_key_layout.addWidget(QLabel("API Key:"))
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setPlaceholderText("使用 ElevenLabs 或 Qwen 时需要...")
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_edit.setEnabled(False)
        api_key_layout.addWidget(self.api_key_edit)
        
        # Qwen API URL 输入
        api_url_layout = QHBoxLayout()
        api_url_layout.addWidget(QLabel("API URL:"))
        self.api_url_edit = QLineEdit()
        self.api_url_edit.setPlaceholderText("第三方 API 或 DashScope URL")
        self.api_url_edit.setText("https://dashscope-intl.aliyuncs.com/api/v1")
        self.api_url_edit.setEnabled(False)
        api_url_layout.addWidget(self.api_url_edit)
        
        # API 类型提示
        self.api_type_label = QLabel("(支持第三方 API: /v1/audio/transcriptions)")
        self.api_type_label.setStyleSheet("color: gray; font-size: 10px;")
        api_url_layout.addWidget(self.api_type_label)
        api_url_layout.addStretch()
        
        engine_layout.addLayout(engine_select_layout)
        engine_layout.addLayout(api_key_layout)
        engine_layout.addLayout(api_url_layout)
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
        self.model_combo.addItems(["tiny", "base", "small", "medium", "large"])
        self.model_combo.setCurrentText("base")
        model_layout.addWidget(self.model_combo)
        self.model_hint_label = QLabel("(tiny最快, large最准确)")
        model_layout.addWidget(self.model_hint_label)
        model_layout.addStretch()
        
        # 语言选择（ElevenLabs）
        lang_layout = QHBoxLayout()
        lang_layout.addWidget(QLabel("语言:"))
        self.lang_combo = QComboBox()
        self.lang_combo.addItems([
            "自动检测",
            "eng - 英语",
            "chi - 中文",
            "spa - 西班牙语",
            "fra - 法语",
            "deu - 德语",
            "jpn - 日语",
            "kor - 韩语"
        ])
        self.lang_combo.setEnabled(False)
        lang_layout.addWidget(self.lang_combo)
        
        # 说话人识别（ElevenLabs）
        self.diarize_check = QCheckBox("启用说话人识别 (标注谁在说话)")
        self.diarize_check.setEnabled(False)
        lang_layout.addWidget(self.diarize_check)
        lang_layout.addStretch()
        
        # 断句设置（Whisper）
        segment_layout = QHBoxLayout()
        segment_layout.addWidget(QLabel("断句设置:"))
        
        segment_layout.addWidget(QLabel("停顿阈值:"))
        self.pause_threshold_spin = QDoubleSpinBox()
        self.pause_threshold_spin.setRange(0.1, 3.0)
        self.pause_threshold_spin.setSingleStep(0.1)
        self.pause_threshold_spin.setValue(0.5)
        self.pause_threshold_spin.setDecimals(1)
        self.pause_threshold_spin.setSuffix(" 秒")
        self.pause_threshold_spin.setToolTip("超过此时间的停顿会分成新段落")
        segment_layout.addWidget(self.pause_threshold_spin)
        
        segment_layout.addWidget(QLabel("每段最大词数:"))
        self.max_words_spin = QSpinBox()
        self.max_words_spin.setRange(5, 50)
        self.max_words_spin.setValue(12)
        self.max_words_spin.setToolTip("每个字幕段落的最大词数")
        segment_layout.addWidget(self.max_words_spin)
        
        segment_layout.addStretch()
        
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
        output_layout.addLayout(segment_layout)
        output_layout.addLayout(vad_layout)
        output_group.setLayout(output_layout)
        
        # 执行按钮
        button_layout = QHBoxLayout()
        self.process_btn = QPushButton("开始识别")
        self.process_btn.clicked.connect(self.process_asr)
        self.save_settings_btn = QPushButton("保存设置")
        self.save_settings_btn.clicked.connect(self.save_settings_manually)
        self.refresh_models_btn = QPushButton("刷新模型")
        self.refresh_models_btn.clicked.connect(self.refresh_models)
        button_layout.addWidget(self.process_btn)
        button_layout.addWidget(self.save_settings_btn)
        button_layout.addWidget(self.refresh_models_btn)
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
        """当 ASR 引擎切换时更新界面"""
        engine_text = self.engine_combo.currentText()
        
        is_whisper = "Whisper" in engine_text
        is_elevenlabs = "ElevenLabs" in engine_text
        is_qwen = "Qwen" in engine_text
        
        # 启用/禁用相关控件
        self.api_key_edit.setEnabled(not is_whisper)
        self.api_url_edit.setEnabled(is_qwen)
        self.api_type_label.setVisible(is_qwen)
        self.url_input_edit.setEnabled(is_qwen)  # URL 输入仅 Qwen 可用
        self.qwen_hint_label.setVisible(is_qwen)  # 显示/隐藏 Qwen 提示
        self.model_combo.setEnabled(True)
        self.lang_combo.setEnabled(is_elevenlabs or is_qwen)
        self.diarize_check.setEnabled(is_elevenlabs)
        
        # VAD 控件仅 Whisper 可用
        self.vad_check.setEnabled(is_whisper)
        self.vad_threshold_spin.setEnabled(is_whisper and self.vad_check.isChecked())
        self.vad_hint_label.setVisible(is_whisper)
        
        # 更新模型列表
        if is_qwen:
            self.model_combo.clear()
            # 尝试从远端获取模型列表
            models = self.fetch_qwen_models()
            if models:
                self.model_combo.addItems(models)
            else:
                # 回退到默认列表
                self.model_combo.addItems([
                    "qwen3-asr-flash (支持本地上传)",
                    "qwen3-asr-flash-filetrans (需要 URL)",
                    "qwen2-audio-turbo"
                ])
            self.model_combo.setCurrentIndex(0)  # 默认选择第一个
            self.model_hint_label.setText("(推荐 flash 用于本地文件)")
        elif is_whisper:
            self.model_combo.clear()
            self.model_combo.addItems(["tiny", "base", "small", "medium", "large"])
            self.model_combo.setCurrentText("base")
            self.model_hint_label.setText("(需要 PyTorch，如有问题推荐用 ElevenLabs)")
        else:
            self.model_combo.setEnabled(False)
            self.model_hint_label.setText("")
    
    def load_api_key_from_config(self):
        """从配置文件加载设置"""
        import json
        try:
            with open("config.json", "r") as f:
                config = json.load(f)
                
                # 加载 ASR 设置
                asr_config = config.get("asr_settings", {})
                
                # 恢复引擎选择（先恢复引擎，这样才能正确设置其他控件）
                engine = asr_config.get("engine", "Whisper (本地, 免费)")
                index = self.engine_combo.findText(engine, Qt.MatchFlag.MatchContains)
                if index >= 0:
                    self.engine_combo.setCurrentIndex(index)
                
                # 加载 API Key（根据引擎类型加载对应的 key）
                if "Qwen" in engine:
                    api_key = config.get("qwen_api_key", config.get("elevenlabs_api_key", ""))
                else:
                    api_key = config.get("elevenlabs_api_key", "")
                
                if api_key:
                    self.api_key_edit.setText(api_key)
                
                # 恢复模型选择
                model = asr_config.get("model", "base")
                model_index = self.model_combo.findText(model)
                if model_index >= 0:
                    self.model_combo.setCurrentIndex(model_index)
                
                # 恢复 API URL
                api_url = asr_config.get("api_url", "https://dashscope-intl.aliyuncs.com/api/v1")
                self.api_url_edit.setText(api_url)
                
                # 恢复语言选择
                language = asr_config.get("language", "自动检测")
                lang_index = self.lang_combo.findText(language)
                if lang_index >= 0:
                    self.lang_combo.setCurrentIndex(lang_index)
                
                # 恢复说话人识别选项
                diarize = asr_config.get("diarize", False)
                self.diarize_check.setChecked(diarize)
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
            
            # 更新 API Key（根据引擎类型保存到对应的字段）
            engine_text = self.engine_combo.currentText()
            if api_key:
                if "Qwen" in engine_text:
                    config["qwen_api_key"] = api_key
                else:
                    config["elevenlabs_api_key"] = api_key
            
            # 保存 ASR 设置
            config["asr_settings"] = {
                "engine": engine_text,
                "model": self.model_combo.currentText(),
                "api_url": self.api_url_edit.text().strip(),
                "language": self.lang_combo.currentText(),
                "diarize": self.diarize_check.isChecked()
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
    
    def fetch_qwen_models(self, verbose=False):
        """从远端获取 Qwen 模型列表"""
        import requests
        
        api_url = self.api_url_edit.text().strip()
        api_key = self.api_key_edit.text().strip()
        
        if verbose:
            self.log(f"📋 当前配置:")
            self.log(f"  API URL: {api_url}")
            self.log(f"  API Key: {'已配置' if api_key else '未配置'}")
        
        # 如果没有配置 API，使用默认列表
        if not api_url or not api_key:
            if verbose:
                self.log("❌ 未配置 API URL 或 API Key")
            return None
        
        try:
            # 检查 API URL 格式
            is_openai_compatible = '/v1/' in api_url or 'openai' in api_url.lower() or api_url.startswith('http')
            
            if verbose:
                self.log(f"API 类型检测: {'OpenAI 兼容' if is_openai_compatible else 'DashScope'}")
            
            # 尝试获取模型列表（OpenAI 兼容 API）
            if is_openai_compatible:
                # 构建 models URL
                if '/v1/audio/transcriptions' in api_url:
                    models_url = api_url.replace('/v1/audio/transcriptions', '/v1/models')
                elif '/audio/transcriptions' in api_url:
                    models_url = api_url.replace('/audio/transcriptions', '/v1/models')
                elif api_url.endswith('/v1') or api_url.endswith('/v1/'):
                    models_url = api_url.rstrip('/') + '/models'
                else:
                    # 假设是基础 URL
                    models_url = api_url.rstrip('/') + '/v1/models'
                
                if verbose:
                    self.log(f"构建的 models URL: {models_url}")
                
                # 隐藏部分 API Key 用于显示
                masked_key = api_key[:8] + '...' + api_key[-4:] if len(api_key) > 12 else '***'
                
                headers = {
                    'Authorization': f'Bearer {api_key}',
                    'Accept': 'application/json'
                }
                
                if verbose:
                    self.log("=" * 50)
                    self.log("📡 请求模型列表")
                    self.log(f"URL: {models_url}")
                    self.log(f"Method: GET")
                    self.log(f"Headers:")
                    self.log(f"  - Authorization: Bearer {masked_key}")
                    self.log(f"  - Accept: application/json")
                    self.log("=" * 50)
                
                print(f"Fetching models from: {models_url}")
                response = requests.get(models_url, headers=headers, timeout=10)
                
                if verbose:
                    self.log(f"📥 响应状态: {response.status_code}")
                    self.log(f"响应头: Content-Type={response.headers.get('Content-Type', 'N/A')}")
                
                if response.status_code == 200:
                    data = response.json()
                    
                    if verbose:
                        self.log(f"响应数据结构: {list(data.keys()) if isinstance(data, dict) else type(data)}")
                    
                    # 解析模型列表
                    models = []
                    if 'data' in data:
                        if verbose:
                            self.log(f"找到 {len(data['data'])} 个模型")
                        
                        for model in data['data']:
                            model_id = model.get('id', '')
                            if verbose:
                                self.log(f"  - {model_id}")
                            
                            if 'asr' in model_id.lower() or 'whisper' in model_id.lower() or 'audio' in model_id.lower():
                                # 添加描述
                                if 'flash' in model_id and 'filetrans' not in model_id:
                                    models.append(f"{model_id} (支持本地上传)")
                                elif 'filetrans' in model_id:
                                    models.append(f"{model_id} (需要 URL)")
                                else:
                                    models.append(model_id)
                    
                    if models:
                        if verbose:
                            self.log(f"✅ 成功获取 {len(models)} 个 ASR 模型:")
                            for m in models:
                                self.log(f"  ✓ {m}")
                        print(f"Fetched {len(models)} models from API")
                        return models
                    else:
                        if verbose:
                            self.log("⚠️ 未找到 ASR 相关模型")
                else:
                    if verbose:
                        self.log(f"❌ 请求失败: {response.status_code}")
                        try:
                            self.log(f"错误信息: {response.text[:500]}")
                        except:
                            pass
            else:
                if verbose:
                    self.log("⚠️ API URL 不是 OpenAI 兼容格式")
                    self.log(f"当前 URL: {api_url}")
                    self.log("提示: URL 应包含 '/v1/' 或以 'http' 开头")
            
            # DashScope API 模型列表（如果支持）
            # 这里可以添加 DashScope 特定的模型获取逻辑
            
        except requests.exceptions.Timeout:
            if verbose:
                self.log("❌ 请求超时（10秒）")
            print("Model fetch timeout, using default list")
        except requests.exceptions.ConnectionError as e:
            if verbose:
                self.log(f"❌ 连接错误: {str(e)}")
        except Exception as e:
            if verbose:
                self.log(f"❌ 获取失败: {type(e).__name__}: {str(e)}")
            print(f"Failed to fetch models: {e}")
        
        return None
    
    def refresh_models(self):
        """手动刷新模型列表"""
        engine_text = self.engine_combo.currentText()
        if "Qwen" not in engine_text:
            self.log("只有 Qwen ASR 支持刷新模型列表")
            return
        
        self.log("🔄 正在从 API 获取模型列表...")
        
        # 使用详细模式获取模型
        models = self.fetch_qwen_models(verbose=True)
        
        if models:
            current_model = self.model_combo.currentText()
            self.model_combo.clear()
            self.model_combo.addItems(models)
            
            # 尝试恢复之前选择的模型
            index = self.model_combo.findText(current_model)
            if index >= 0:
                self.model_combo.setCurrentIndex(index)
            
            self.log("=" * 50)
            self.log(f"✅ 刷新完成！共 {len(models)} 个模型可用")
        else:
            self.log("=" * 50)
            self.log("❌ 无法获取模型列表")
            self.log("请检查:")
            self.log("  1. API URL 是否正确")
            self.log("  2. API Key 是否有效")
            self.log("  3. 网络连接是否正常")
            self.log("  4. API 是否支持 /v1/models 端点")
    
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
        
        # 检查是否使用 Qwen 且提供了 URL
        engine_text = self.engine_combo.currentText()
        is_qwen = "Qwen" in engine_text
        audio_url = self.url_input_edit.text().strip() if is_qwen else None
        
        # 验证输入
        if is_qwen and audio_url:
            # 使用 URL 模式
            if not output_path:
                self.log("请选择输出文件")
                return
            # audio_path 将被设置为 URL
            audio_path = audio_url
            self.log(f"使用 URL: {audio_url}")
        else:
            # 使用本地文件模式
            if not audio_path or not output_path:
                self.log("请选择输入和输出文件")
                return
            
            if not os.path.exists(audio_path):
                self.log("输入文件不存在")
                return
            
            if is_qwen:
                model_name = self.model_combo.currentText()
                if "filetrans" in model_name:
                    self.log("警告: filetrans 模型需要公网 URL。建议使用 qwen3-asr-flash 处理本地文件。")
                    self.log("或将文件上传到 OSS 后，在 '或 URL' 输入框中输入 URL")
        
        # 确定使用的引擎
        engine_text = self.engine_combo.currentText()
        if "ElevenLabs" in engine_text:
            engine_type = "elevenlabs"
        elif "Qwen" in engine_text:
            engine_type = "qwen"
        else:
            engine_type = "whisper"
        
        # 准备参数
        api_key = None
        api_url = None
        language_code = None
        diarize = False
        
        if engine_type == "elevenlabs":
            api_key = self.api_key_edit.text().strip()
            if not api_key:
                self.log("请输入 ElevenLabs API Key")
                return
            
            # 获取语言代码
            lang_text = self.lang_combo.currentText()
            if lang_text != "自动检测":
                language_code = lang_text.split(" - ")[0]
            
            diarize = self.diarize_check.isChecked()
        
        elif engine_type == "qwen":
            api_key = self.api_key_edit.text().strip()
            if not api_key:
                self.log("请输入 Qwen API Key")
                return
            
            # 获取 API URL
            api_url = self.api_url_edit.text().strip()
            
            # 获取语言代码
            lang_text = self.lang_combo.currentText()
            if lang_text != "自动检测":
                language_code = lang_text.split(" - ")[0]
        
        self.process_btn.setEnabled(False)
        self.progress_bar.show()
        
        # 获取断句参数
        pause_threshold = self.pause_threshold_spin.value()
        max_words = self.max_words_spin.value()
        
        self.log(f"开始语音识别 (使用 {engine_type.upper()})...")
        self.log(f"断句设置: 停顿阈值={pause_threshold}s, 每段最大词数={max_words}")
        
        # VAD 参数（仅 Whisper）
        use_vad = self.vad_check.isChecked() if engine_type == "whisper" else False
        vad_threshold = self.vad_threshold_spin.value()
        
        if use_vad and engine_type == "whisper":
            self.log(f"Silero-VAD 已启用 (阈值: {vad_threshold})")
        
        self.thread = ASRThread(
            audio_path, output_path, 
            self.model_combo.currentText(),
            engine_type,
            api_key,
            language_code,
            diarize,
            api_url,
            pause_threshold=pause_threshold,
            max_words_per_segment=max_words,
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
        
        # 如果成功且使用了 API，自动保存配置
        if success:
            engine_text = self.engine_combo.currentText()
            if "ElevenLabs" in engine_text or "Qwen" in engine_text:
                self.save_api_key_to_config()
    
    def on_vad_changed(self, state):
        """当 VAD 选项改变时"""
        enabled = state == Qt.CheckState.Checked.value
        self.vad_threshold_spin.setEnabled(enabled)
    
    def log(self, message):
        console_info(message, "语音识别")
