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
                 use_vad=True, vad_threshold=0.5, initial_prompt=None,
                 ai_optimize=False, ai_level="medium", ai_config=None):
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
        # Prompt 参数
        self.initial_prompt = initial_prompt
        # AI 精修参数
        self.ai_optimize = ai_optimize
        self.ai_level = ai_level
        self.ai_config = ai_config or {}
    
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
            # 设置 Prompt（专有名词提示）
            if self.initial_prompt:
                processor.initial_prompt = self.initial_prompt
                self.progress.emit(f"使用专有名词提示: {self.initial_prompt[:30]}...")
            
            vad_info = f", VAD: {'启用' if self.use_vad else '禁用'}" if self.engine_type == "whisper" else ""
            self.progress.emit(f"开始转录... (停顿阈值: {self.pause_threshold}s, 每段最大词数: {self.max_words_per_segment}{vad_info})")
            
            # 获取 AI 配置
            ai_api_key = self.ai_config.get("api_key") if self.ai_optimize else None
            ai_api_url = self.ai_config.get("api_url") if self.ai_optimize else None
            ai_model = self.ai_config.get("model") if self.ai_optimize else None
            
            if self.ai_optimize and not ai_api_key:
                self.progress.emit("⚠️ AI 精修已启用但未配置 API，请先在翻译模块中配置")
            
            # 转录 + AI 精修（一体化流程）
            processor.transcribe(
                self.audio_path, 
                output_srt_path=self.output_path,
                language_code=self.language_code,
                diarize=self.diarize,
                enable_ai_optimize=self.ai_optimize and bool(ai_api_key),
                ai_api_key=ai_api_key,
                ai_api_url=ai_api_url,
                ai_model=ai_model,
                ai_optimize_level=self.ai_level,
                progress_callback=lambda msg: self.progress.emit(msg)
            )
            
            self.finished.emit(True, f"字幕生成成功！保存至: {self.output_path}")
        except Exception as e:
            self.finished.emit(False, f"错误: {str(e)}")


class ASRWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()
        self.thread = None
        self.load_api_key_from_config()
        # 延迟更新 LLM 状态（init_ui 之后）
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(100, self.update_llm_status)
        
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
        
        # 专有名词提示（Prompt）设置
        prompt_layout = QHBoxLayout()
        prompt_layout.addWidget(QLabel("技术领域:"))
        self.prompt_combo = QComboBox()
        self.prompt_combo.addItems([
            "无 - 不使用提示词",
            "Godot - 游戏引擎",
            "Unity - 游戏引擎",
            "Unreal - 游戏引擎",
            "Web - 前端开发",
            "AI/ML - 人工智能",
            "Maya - Autodesk 3D",
            "3ds Max - Autodesk 3D",
            "Blender - 开源3D",
            "Houdini - 特效模拟",
            "Cinema 4D - Maxon 3D",
            "ZBrush - 数字雕刻",
            "After Effects - Adobe合成",
            "Nuke - The Foundry合成",
            "DaVinci Resolve - 调色剪辑",
            "Substance - Adobe材质",
            "自定义..."
        ])
        self.prompt_combo.setToolTip("选择技术领域可帮助 Whisper 更准确识别专有名词")
        self.prompt_combo.currentTextChanged.connect(self.on_prompt_changed)
        prompt_layout.addWidget(self.prompt_combo)
        
        self.custom_prompt_edit = QLineEdit()
        self.custom_prompt_edit.setPlaceholderText("输入专有名词，用逗号分隔...")
        self.custom_prompt_edit.setToolTip("例如: Godot, GDScript, OnReady, Wayland, VS Code")
        self.custom_prompt_edit.hide()
        prompt_layout.addWidget(self.custom_prompt_edit)
        prompt_layout.addStretch()
        
        output_layout.addLayout(output_file_layout)
        output_layout.addLayout(model_layout)
        output_layout.addLayout(lang_layout)
        # output_layout.addLayout(segment_layout)  # 断句设置暂时隐藏
        output_layout.addLayout(vad_layout)
        output_layout.addLayout(prompt_layout)
        output_group.setLayout(output_layout)
        
        # AI 精修选项（使用全局 LLM 配置）
        ai_group = QGroupBox("AI 精修 (可选)")
        ai_layout = QVBoxLayout()
        
        # LLM 状态行
        llm_row = QHBoxLayout()
        self.llm_status_label = QLabel("LLM: 未配置")
        self.llm_status_label.setStyleSheet("color: orange;")
        llm_row.addWidget(self.llm_status_label)
        
        self.open_llm_config_btn = QPushButton("配置 LLM")
        self.open_llm_config_btn.clicked.connect(self.open_llm_config)
        llm_row.addWidget(self.open_llm_config_btn)
        llm_row.addStretch()
        
        ai_row1 = QHBoxLayout()
        self.ai_optimize_check = QCheckBox("启用 AI 精修")
        self.ai_optimize_check.setToolTip("使用 AI 修正术语、合并破碎句子、去除口语填充词")
        self.ai_optimize_check.stateChanged.connect(self.on_ai_optimize_changed)
        ai_row1.addWidget(self.ai_optimize_check)
        
        ai_row1.addWidget(QLabel("精修强度:"))
        self.ai_level_combo = QComboBox()
        self.ai_level_combo.addItems(["轻度 (仅断句)", "中度 (推荐)", "重度 (完全重写)"])
        self.ai_level_combo.setCurrentIndex(1)
        self.ai_level_combo.setEnabled(False)
        self.ai_level_combo.setToolTip("轻度: 只调整断句\n中度: 修正术语+合并句子+去口语化\n重度: 完全重写使其流畅")
        ai_row1.addWidget(self.ai_level_combo)
        ai_row1.addStretch()
        
        self.ai_hint_label = QLabel("💡 AI 精修可修正 Wayland/QoL/OnReady 等术语，合并破碎句子")
        self.ai_hint_label.setStyleSheet("color: #4A90E2; font-size: 11px;")
        
        ai_layout.addLayout(llm_row)
        ai_layout.addLayout(ai_row1)
        ai_layout.addWidget(self.ai_hint_label)
        ai_group.setLayout(ai_layout)
        
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
        layout.addWidget(ai_group)
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
    
    def on_prompt_changed(self, text):
        """当技术领域选择变化时"""
        if "自定义" in text:
            self.custom_prompt_edit.show()
        else:
            self.custom_prompt_edit.hide()
    
    def get_prompt(self):
        """获取当前的 prompt 设置"""
        prompt_text = self.prompt_combo.currentText()
        
        if "自定义" in prompt_text:
            return self.custom_prompt_edit.text().strip() or None
        elif "无" in prompt_text:
            return None
        elif "Godot" in prompt_text:
            return "Godot, GDScript, Node, Scene, Signal, Export, OnReady, TileMap, Wayland, OpenXR, VS Code, PR, QoL, Dev1, Dev2"
        elif "Unity" in prompt_text:
            return "Unity, C#, GameObject, MonoBehaviour, Prefab, Inspector, Hierarchy, Asset, Shader, HDRP, URP"
        elif "Unreal" in prompt_text:
            return "Unreal Engine, Blueprint, C++, Actor, Component, Level, Material, Niagara, Lumen, Nanite"
        elif "Web" in prompt_text:
            return "JavaScript, TypeScript, React, Vue, Angular, Node.js, npm, API, REST, GraphQL, CSS, HTML"
        elif "AI" in prompt_text:
            return "AI, ML, LLM, GPT, Transformer, PyTorch, TensorFlow, CUDA, GPU, API, Prompt, Fine-tuning"
        elif "Maya" in prompt_text:
            return "Maya, Arnold, MEL, Python, Viewport, Outliner, Hypershade, UV, NURBS, Polygon, Rigging, Skinning, Blend Shape, IK, FK, Animation, Keyframe, Graph Editor"
        elif "3ds Max" in prompt_text:
            return "3ds Max, V-Ray, Corona, MaxScript, Modifier, Editable Poly, Unwrap UVW, Biped, CAT, Particle Flow, MassFX, Arnold"
        elif "Blender" in prompt_text:
            return "Blender, Cycles, Eevee, Geometry Nodes, Shader Editor, Compositor, Grease Pencil, Sculpt Mode, Weight Paint, UV Unwrap, Modifier, Add-on, Python, HDRI"
        elif "Houdini" in prompt_text:
            return "Houdini, VEX, Karma, Solaris, PDG, TOPs, SOPs, DOPs, COPs, Vellum, Pyro, FLIP, RBD, Procedural, HDA, Attribute, Wrangle, Point Cloud"
        elif "Cinema 4D" in prompt_text or "C4D" in prompt_text:
            return "Cinema 4D, C4D, Redshift, Octane, MoGraph, Cloner, Effector, Field, Xpresso, BodyPaint, Sculpt, Dynamics, Cloth, Hair, Python, COFFEE"
        elif "ZBrush" in prompt_text:
            return "ZBrush, Sculpt, ZSphere, DynaMesh, ZRemesher, Polygroups, SubTool, Brush, Alpha, MatCap, Polypaint, Fibermesh, GoZ, Decimation Master"
        elif "After Effects" in prompt_text or "AE" in prompt_text:
            return "After Effects, AE, Composition, Layer, Keyframe, Expression, Mask, Track Matte, Pre-comp, Render Queue, Effect, Plugin, Motion Blur, Roto Brush, Puppet Tool"
        elif "Nuke" in prompt_text:
            return "Nuke, Node, Merge, Roto, RotoPaint, Tracker, CameraTracker, Keyer, Primatte, Grade, ColorCorrect, Denoise, Deep, EXR, ACES, LUT"
        elif "DaVinci" in prompt_text:
            return "DaVinci Resolve, Fusion, Color Page, Edit Page, Fairlight, Node, Power Window, Qualifier, LUT, ACES, HDR, Dolby Vision, Timeline, Media Pool"
        elif "Substance" in prompt_text:
            return "Substance 3D Painter, Substance Designer, Substance Sampler, PBR, Material, Texture, Bake, Smart Material, Generator, Filter, Export, UDIM, Normal Map, Roughness"
        return None
    
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
        
        # 获取 Prompt
        initial_prompt = self.get_prompt()
        
        self.log(f"开始语音识别 (使用 Faster-Whisper)...")
        self.log(f"模型: {self.model_combo.currentText()}")
        if use_vad:
            self.log(f"VAD 已启用 (阈值: {vad_threshold})")
        if initial_prompt:
            self.log(f"专有名词提示: {initial_prompt[:40]}...")
        
        # AI 精修参数
        ai_optimize = self.ai_optimize_check.isChecked()
        ai_level = "light"
        ai_level_text = self.ai_level_combo.currentText()
        if "中度" in ai_level_text:
            ai_level = "medium"
        elif "重度" in ai_level_text:
            ai_level = "heavy"
        
        ai_config = None
        if ai_optimize:
            ai_config = self.get_translation_api_config()
            if ai_config and ai_config.get("api_key"):
                self.log(f"✓ AI 精修已启用 (强度: {ai_level_text})")
                self.log(f"  API: {ai_config.get('api_url', '')[:50]}...")
                self.log(f"  模型: {ai_config.get('model', 'deepseek-chat')}")
            else:
                self.log("⚠️ AI 精修需要先在翻译模块中配置 API Key！")
                self.log("  请到「字幕翻译」页面配置 API Key 后重试")
                ai_optimize = False  # 禁用 AI 优化
        
        self.thread = ASRThread(
            audio_path, output_path, 
            self.model_combo.currentText(),
            engine_type,
            api_key=None,
            language_code=language_code,
            diarize=False,
            api_url=None,
            pause_threshold=0.3,      # 更敏感的断句
            max_words_per_segment=10, # 更短的字幕
            use_vad=use_vad,
            vad_threshold=vad_threshold,
            initial_prompt=initial_prompt,
            ai_optimize=ai_optimize,
            ai_level=ai_level,
            ai_config=ai_config
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
    
    def on_ai_optimize_changed(self, state):
        """当 AI 精修选项改变时"""
        enabled = state == Qt.CheckState.Checked.value
        self.ai_level_combo.setEnabled(enabled)
        
        # 检查 LLM 配置
        if enabled:
            llm_config = self.get_translation_api_config()
            if not llm_config or not llm_config.get("api_key"):
                self.log("⚠️ 请先配置 LLM（点击「配置 LLM」按钮）")
    
    def open_llm_config(self):
        """打开全局 LLM 配置对话框"""
        from video_tool.gui.llm_config_dialog import LLMConfigDialog
        dialog = LLMConfigDialog(self)
        if dialog.exec():
            self.update_llm_status()
    
    def update_llm_status(self):
        """更新 LLM 配置状态显示"""
        try:
            llm_config = self.get_translation_api_config()
            print(f"[DEBUG] ASR LLM config: {llm_config}")
            
            if llm_config and llm_config.get("api_key"):
                model = llm_config.get("model", "deepseek-chat")
                self.llm_status_label.setText(f"LLM: ✓ {model}")
                self.llm_status_label.setStyleSheet("color: green;")
            else:
                self.llm_status_label.setText("LLM: 未配置")
                self.llm_status_label.setStyleSheet("color: orange;")
        except Exception as e:
            print(f"[DEBUG] update_llm_status error: {e}")
            self.llm_status_label.setText("LLM: 未配置")
            self.llm_status_label.setStyleSheet("color: orange;")
    
    def get_translation_api_config(self):
        """获取全局 LLM 配置"""
        import json
        import os
        try:
            config_path = "config.json"
            print(f"[DEBUG] Reading config from: {os.path.abspath(config_path)}")
            
            if not os.path.exists(config_path):
                print(f"[DEBUG] Config file not found")
                return None
                
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
                print(f"[DEBUG] Config keys: {config.keys()}")
                
                # 优先使用全局 LLM 配置
                llm_config = config.get("llm_settings", {})
                print(f"[DEBUG] llm_settings: {llm_config}")
                
                if llm_config.get("api_key"):
                    return {
                        "api_key": llm_config.get("api_key", ""),
                        "api_url": llm_config.get("api_url", "https://api.deepseek.com/v1/chat/completions"),
                        "model": llm_config.get("model", "deepseek-chat")
                    }
                # 回退到翻译模块配置
                subtitle_config = config.get("subtitle_settings", {})
                print(f"[DEBUG] subtitle_settings: {subtitle_config}")
                
                return {
                    "api_key": subtitle_config.get("api_key", ""),
                    "api_url": subtitle_config.get("api_url", "https://api.deepseek.com/v1/chat/completions"),
                    "model": subtitle_config.get("model", "deepseek-chat")
                }
        except Exception as e:
            print(f"[DEBUG] get_translation_api_config error: {e}")
            return None
    
    def log(self, message):
        console_info(message, "语音识别")
