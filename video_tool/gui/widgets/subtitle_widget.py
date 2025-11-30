from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QLineEdit, QPushButton, QFileDialog, QTextEdit,
                             QGroupBox, QComboBox, QProgressBar, QSpinBox,
                             QDoubleSpinBox, QFontComboBox, QFrame, QSplitter, QScrollArea)
from PyQt6.QtCore import QThread, pyqtSignal, Qt
from PyQt6.QtGui import QFont, QColor, QTextCharFormat, QPainter, QPen, QBrush
from .console_widget import console_info, console_error, console_warning
import os
import json


class TranslateThread(QThread):
    """Background thread for translation."""
    progress = pyqtSignal(int, int)
    finished = pyqtSignal(list, list)  # translated, original
    error = pyqtSignal(str)
    log = pyqtSignal(str)
    
    def __init__(self, manager, subtitles, target_lang, prompt_text, source_path, max_retry_rounds=2):
        super().__init__()
        self.manager = manager
        self.subtitles = subtitles
        self.target_lang = target_lang
        self.prompt_text = prompt_text
        self.source_path = source_path
        self.max_retry_rounds = max_retry_rounds
    
    def _find_untranslated(self, translated_subs, original_subs):
        """找出未翻译的字幕索引"""
        untranslated_indices = []
        for i, (trans, orig) in enumerate(zip(translated_subs, original_subs)):
            if trans['text'] == orig['text'] and len(orig['text'].strip()) > 5:
                untranslated_indices.append(i)
        return untranslated_indices
    
    def run(self):
        try:
            self.log.emit(f"开始翻译 {len(self.subtitles)} 条字幕...")
            original_subs = [sub.copy() for sub in self.subtitles]
            
            result = self.manager.translate_subtitles(
                self.subtitles,
                self.target_lang,
                self.prompt_text,
                progress_callback=lambda cur, total: self.progress.emit(cur, total)
            )
            
            for retry_round in range(self.max_retry_rounds):
                untranslated_indices = self._find_untranslated(result, original_subs)
                
                if not untranslated_indices:
                    self.log.emit("✓ 所有字幕翻译检查通过")
                    break
                
                self.log.emit(f"\n检测到 {len(untranslated_indices)} 条未翻译，开始第 {retry_round + 1} 轮补译...")
                self.log.emit(f"未翻译序号: {[i+1 for i in untranslated_indices[:10]]}" + 
                             ("..." if len(untranslated_indices) > 10 else ""))
                
                retry_subs = [original_subs[i].copy() for i in untranslated_indices]
                old_thread_count = self.manager.thread_count
                self.manager.set_thread_count(1)
                
                try:
                    retry_result = self.manager.translate_subtitles(
                        retry_subs,
                        self.target_lang,
                        self.prompt_text,
                        progress_callback=lambda cur, total: self.log.emit(f"  补译进度: {cur}/{total}")
                    )
                    
                    success_count = 0
                    for j, idx in enumerate(untranslated_indices):
                        if retry_result[j]['text'] != original_subs[idx]['text']:
                            result[idx] = retry_result[j]
                            success_count += 1
                    
                    self.log.emit(f"  第 {retry_round + 1} 轮补译完成: {success_count}/{len(untranslated_indices)} 条成功")
                finally:
                    self.manager.set_thread_count(old_thread_count)
            
            final_untranslated = self._find_untranslated(result, original_subs)
            if final_untranslated:
                self.log.emit(f"\n⚠ 仍有 {len(final_untranslated)} 条未能翻译")
            
            self.finished.emit(result, original_subs)
        except Exception as e:
            self.error.emit(str(e))


class SubtitlePreviewWidget(QFrame):
    """字幕预览组件"""
    def __init__(self):
        super().__init__()
        self.setMinimumSize(320, 180)
        self.setStyleSheet("background-color: #1a1a2e; border: 1px solid #333;")
        
        self.cn_font = "Microsoft YaHei"
        self.cn_size = 24
        self.cn_color = "#FFFFFF"
        self.en_font = "Arial"
        self.en_size = 16
        self.en_color = "#CCCCCC"
        
        self.cn_text = "这是中文字幕示例"
        self.en_text = "This is English subtitle example"
    
    def set_cn_style(self, font, size, color):
        self.cn_font = font
        self.cn_size = size
        self.cn_color = color
        self.update()
    
    def set_en_style(self, font, size, color):
        self.en_font = font
        self.en_size = size
        self.en_color = color
        self.update()
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        painter.fillRect(self.rect(), QColor("#1a1a2e"))
        video_rect = self.rect().adjusted(10, 10, -10, -10)
        painter.fillRect(video_rect, QColor("#0f0f1a"))
        
        center_x = video_rect.center().x()
        bottom_y = video_rect.bottom() - 20
        
        en_font = QFont(self.en_font, self.en_size)
        painter.setFont(en_font)
        painter.setPen(QPen(QColor("#000000")))
        en_metrics = painter.fontMetrics()
        en_width = en_metrics.horizontalAdvance(self.en_text)
        en_x = center_x - en_width // 2
        en_y = bottom_y
        for dx, dy in [(-1,-1), (-1,1), (1,-1), (1,1)]:
            painter.drawText(en_x + dx, en_y + dy, self.en_text)
        painter.setPen(QPen(QColor(self.en_color)))
        painter.drawText(en_x, en_y, self.en_text)
        
        cn_font = QFont(self.cn_font, self.cn_size)
        painter.setFont(cn_font)
        cn_metrics = painter.fontMetrics()
        cn_width = cn_metrics.horizontalAdvance(self.cn_text)
        cn_x = center_x - cn_width // 2
        cn_y = en_y - en_metrics.height() - 5
        painter.setPen(QPen(QColor("#000000")))
        for dx, dy in [(-1,-1), (-1,1), (1,-1), (1,1)]:
            painter.drawText(cn_x + dx, cn_y + dy, self.cn_text)
        painter.setPen(QPen(QColor(self.cn_color)))
        painter.drawText(cn_x, cn_y, self.cn_text)


class SubtitleWidget(QWidget):
    CONFIG_FILE = "config.json"
    CONFIG_KEY = "subtitle_settings"
    
    def __init__(self):
        super().__init__()
        self.manager = None
        self.current_subtitles = None
        self.original_subtitles = None
        self.translate_thread = None
        self.prompt_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'prompt')
        self.init_ui()
        self.load_settings()

    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # 输入文件组
        input_group = QGroupBox("字幕文件")
        input_layout = QHBoxLayout()
        self.input_edit = QLineEdit()
        self.input_edit.setPlaceholderText("选择字幕文件 (英文)...")
        self.browse_input_btn = QPushButton("浏览")
        self.browse_input_btn.clicked.connect(self.browse_input)
        input_layout.addWidget(self.input_edit)
        input_layout.addWidget(self.browse_input_btn)
        input_group.setLayout(input_layout)

        # 引擎设置组
        engine_group = QGroupBox("翻译引擎")
        engine_layout = QVBoxLayout()
        
        engine_row = QHBoxLayout()
        engine_row.addWidget(QLabel("引擎:"))
        self.engine_combo = QComboBox()
        self.engine_combo.addItems(["Deepseek", "LongCat", "OpenRouter", "DeepLX (非AI)", "自定义第三方"])
        self.engine_combo.currentIndexChanged.connect(self.on_engine_changed)
        engine_row.addWidget(self.engine_combo)
        engine_row.addStretch()
        
        api_url_row = QHBoxLayout()
        api_url_row.addWidget(QLabel("API URL:"))
        self.api_url_edit = QLineEdit()
        self.api_url_edit.setPlaceholderText("https://api.deepseek.com/v1/chat/completions")
        self.api_url_edit.setText("https://api.deepseek.com/v1/chat/completions")
        self.api_url_edit.editingFinished.connect(self.save_settings)
        api_url_row.addWidget(self.api_url_edit)
        
        api_key_row = QHBoxLayout()
        api_key_row.addWidget(QLabel("API Key:"))
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setPlaceholderText("输入 API Key...")
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_edit.editingFinished.connect(self.save_settings)
        api_key_row.addWidget(self.api_key_edit)
        
        model_row = QHBoxLayout()
        model_row.addWidget(QLabel("模型:"))
        self.model_edit = QLineEdit()
        self.model_edit.setText("deepseek-chat")
        self.model_edit.setPlaceholderText("deepseek-chat")
        self.model_edit.editingFinished.connect(self.save_settings)
        model_row.addWidget(self.model_edit)
        
        engine_layout.addLayout(engine_row)
        engine_layout.addLayout(api_url_row)
        engine_layout.addLayout(api_key_row)
        engine_layout.addLayout(model_row)
        engine_group.setLayout(engine_layout)
        
        # Prompt 设置组
        prompt_group = QGroupBox("Prompt 设置 (AI翻译)")
        prompt_layout = QVBoxLayout()
        
        prompt_select_row = QHBoxLayout()
        prompt_select_row.addWidget(QLabel("Prompt 模板:"))
        self.prompt_combo = QComboBox()
        self.prompt_combo.addItem("默认 (自动)")
        self.load_prompt_files()
        self.prompt_combo.currentIndexChanged.connect(self.on_prompt_changed)
        prompt_select_row.addWidget(self.prompt_combo)
        self.refresh_prompt_btn = QPushButton("刷新")
        self.refresh_prompt_btn.clicked.connect(self.load_prompt_files)
        prompt_select_row.addWidget(self.refresh_prompt_btn)
        
        self.prompt_preview = QTextEdit()
        self.prompt_preview.setPlaceholderText("选择 Prompt 模板或输入自定义 Prompt...")
        self.prompt_preview.setMaximumHeight(60)
        
        prompt_layout.addLayout(prompt_select_row)
        prompt_layout.addWidget(self.prompt_preview)
        prompt_group.setLayout(prompt_layout)
        
        # 字幕样式设置组
        style_group = QGroupBox("字幕样式设置")
        style_main_layout = QHBoxLayout()
        
        style_settings_layout = QVBoxLayout()
        
        cn_label = QLabel("中文字幕:")
        cn_label.setStyleSheet("font-weight: bold;")
        style_settings_layout.addWidget(cn_label)
        
        cn_row1 = QHBoxLayout()
        cn_row1.addWidget(QLabel("字体:"))
        self.cn_font_combo = QFontComboBox()
        self.cn_font_combo.setCurrentFont(QFont("Microsoft YaHei"))
        self.cn_font_combo.currentFontChanged.connect(self.on_style_changed)
        cn_row1.addWidget(self.cn_font_combo)
        cn_row1.addWidget(QLabel("大小:"))
        self.cn_size_spin = QSpinBox()
        self.cn_size_spin.setRange(10, 48)
        self.cn_size_spin.setValue(14)
        self.cn_size_spin.valueChanged.connect(self.on_style_changed)
        cn_row1.addWidget(self.cn_size_spin)
        style_settings_layout.addLayout(cn_row1)
        
        cn_row2 = QHBoxLayout()
        cn_row2.addWidget(QLabel("颜色:"))
        self.cn_color_combo = QComboBox()
        self.cn_color_combo.addItems(["白色", "黄色", "青色", "绿色"])
        self.cn_color_combo.currentIndexChanged.connect(self.on_style_changed)
        cn_row2.addWidget(self.cn_color_combo)
        cn_row2.addStretch()
        style_settings_layout.addLayout(cn_row2)
        
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color: #555;")
        style_settings_layout.addWidget(line)
        
        en_label = QLabel("英文字幕:")
        en_label.setStyleSheet("font-weight: bold;")
        style_settings_layout.addWidget(en_label)
        
        en_row1 = QHBoxLayout()
        en_row1.addWidget(QLabel("字体:"))
        self.en_font_combo = QFontComboBox()
        self.en_font_combo.setCurrentFont(QFont("Arial"))
        self.en_font_combo.currentFontChanged.connect(self.on_style_changed)
        en_row1.addWidget(self.en_font_combo)
        en_row1.addWidget(QLabel("大小:"))
        self.en_size_spin = QSpinBox()
        self.en_size_spin.setRange(8, 36)
        self.en_size_spin.setValue(10)
        self.en_size_spin.valueChanged.connect(self.on_style_changed)
        en_row1.addWidget(self.en_size_spin)
        style_settings_layout.addLayout(en_row1)
        
        en_row2 = QHBoxLayout()
        en_row2.addWidget(QLabel("颜色:"))
        self.en_color_combo = QComboBox()
        self.en_color_combo.addItems(["白色", "浅灰", "黄色", "青色"])
        self.en_color_combo.setCurrentIndex(1)
        self.en_color_combo.currentIndexChanged.connect(self.on_style_changed)
        en_row2.addWidget(self.en_color_combo)
        en_row2.addStretch()
        style_settings_layout.addLayout(en_row2)
        
        style_settings_layout.addStretch()
        
        preview_layout = QVBoxLayout()
        preview_label = QLabel("实时预览:")
        preview_label.setStyleSheet("font-weight: bold;")
        preview_layout.addWidget(preview_label)
        self.preview_widget = SubtitlePreviewWidget()
        self.preview_widget.setMinimumSize(300, 170)
        preview_layout.addWidget(self.preview_widget)
        preview_layout.addStretch()
        
        style_main_layout.addLayout(style_settings_layout, 1)
        style_main_layout.addLayout(preview_layout, 1)
        style_group.setLayout(style_main_layout)
        
        # 操作组
        operation_group = QGroupBox("翻译操作")
        operation_layout = QVBoxLayout()
        
        test_layout = QHBoxLayout()
        self.test_connection_btn = QPushButton("测试连接")
        self.test_connection_btn.clicked.connect(self.test_connection)
        self.connection_status = QLabel("未测试")
        self.connection_status.setStyleSheet("color: gray;")
        test_layout.addWidget(self.test_connection_btn)
        test_layout.addWidget(self.connection_status)
        test_layout.addStretch()
        
        translate_layout = QHBoxLayout()
        translate_layout.addWidget(QLabel("翻译到:"))
        self.lang_combo = QComboBox()
        self.lang_combo.addItems(["中文 (zh)", "日文 (ja)", "韩文 (ko)"])
        translate_layout.addWidget(self.lang_combo)
        
        translate_layout.addWidget(QLabel("并发数:"))
        self.thread_count_combo = QComboBox()
        self.thread_count_combo.addItems(["1", "2", "3", "5", "10"])
        self.thread_count_combo.setCurrentText("3")
        self.thread_count_combo.setToolTip("同时翻译的字幕数量，数值越大速度越快但可能触发API限流")
        translate_layout.addWidget(self.thread_count_combo)
        
        translate_layout.addWidget(QLabel("间隔:"))
        self.interval_spin = QDoubleSpinBox()
        self.interval_spin.setRange(0, 30)
        self.interval_spin.setSingleStep(0.5)
        self.interval_spin.setValue(2.0)
        self.interval_spin.setDecimals(1)
        self.interval_spin.setSuffix(" 秒")
        self.interval_spin.setToolTip("每次翻译请求之间的等待时间，避免触发API限流")
        self.interval_spin.setFixedWidth(80)
        self.interval_spin.valueChanged.connect(self.save_settings)
        translate_layout.addWidget(self.interval_spin)
        
        self.translate_btn = QPushButton("开始翻译并保存")
        self.translate_btn.clicked.connect(self.translate_and_save)
        translate_layout.addWidget(self.translate_btn)
        translate_layout.addStretch()
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        
        operation_layout.addLayout(test_layout)
        operation_layout.addLayout(translate_layout)
        operation_layout.addWidget(self.progress_bar)
        operation_group.setLayout(operation_layout)
        
        layout.addWidget(input_group)
        layout.addWidget(engine_group)
        layout.addWidget(prompt_group)
        layout.addWidget(style_group)
        layout.addWidget(operation_group)
        layout.addStretch()
        
        self.update_preview()

    def load_prompt_files(self):
        current_text = self.prompt_combo.currentText()
        self.prompt_combo.clear()
        self.prompt_combo.addItem("默认 (自动)")
        
        if os.path.exists(self.prompt_dir):
            for filename in os.listdir(self.prompt_dir):
                if filename.endswith('.txt'):
                    self.prompt_combo.addItem(filename)
        
        index = self.prompt_combo.findText(current_text)
        if index >= 0:
            self.prompt_combo.setCurrentIndex(index)
    
    def on_engine_changed(self, index):
        if index == 0:  # Deepseek
            self.api_url_edit.setText("https://api.deepseek.com/v1/chat/completions")
            self.api_url_edit.setEnabled(True)
            self.model_edit.setText("deepseek-chat")
            self.model_edit.setEnabled(True)
            self.api_key_edit.setPlaceholderText("输入 API Key...")
            self.prompt_combo.setEnabled(True)
            self.prompt_preview.setEnabled(True)
            self.refresh_prompt_btn.setEnabled(True)
        elif index == 1:  # 美团LongCat
            self.api_url_edit.setText("https://api.longcat.chat/openai/v1/chat/completions")
            self.api_url_edit.setEnabled(True)
            self.model_edit.setText("LongCat-Flash-Chat")
            self.model_edit.setEnabled(True)
            self.api_key_edit.setPlaceholderText("输入 LongCat API Key...")
            self.prompt_combo.setEnabled(True)
            self.prompt_preview.setEnabled(True)
            self.refresh_prompt_btn.setEnabled(True)
        elif index == 2:  # OpenRouter
            self.api_url_edit.setText("https://openrouter.ai/api/v1/chat/completions")
            self.api_url_edit.setEnabled(True)
            self.model_edit.setText("x-ai/grok-4.1-fast:free")
            self.model_edit.setEnabled(True)
            self.api_key_edit.setPlaceholderText("输入 OpenRouter API Key...")
            self.prompt_combo.setEnabled(True)
            self.prompt_preview.setEnabled(True)
            self.refresh_prompt_btn.setEnabled(True)
        elif index == 3:  # DeepLX
            self.api_url_edit.setText("https://api.deeplx.org/{key}/translate")
            self.api_url_edit.setEnabled(False)
            self.model_edit.setText("")
            self.model_edit.setEnabled(False)
            self.api_key_edit.setPlaceholderText("输入 DeepLX Key (可自定义或留空)")
            self.prompt_combo.setEnabled(False)
            self.prompt_preview.setEnabled(False)
            self.refresh_prompt_btn.setEnabled(False)
        else:  # Custom
            self.api_url_edit.setText("")
            self.api_url_edit.setEnabled(True)
            self.model_edit.setText("")
            self.model_edit.setEnabled(True)
            self.api_key_edit.setPlaceholderText("输入 API Key...")
            self.prompt_combo.setEnabled(True)
            self.prompt_preview.setEnabled(True)
            self.refresh_prompt_btn.setEnabled(True)
        self.save_settings()
    
    def load_settings(self):
        if os.path.exists(self.CONFIG_FILE):
            try:
                with open(self.CONFIG_FILE, 'r', encoding='utf-8') as f:
                    all_config = json.load(f)
                
                config = all_config.get(self.CONFIG_KEY, {})
                engine_index = config.get("engine_index", 0)
                self.engine_combo.setCurrentIndex(engine_index)
                self.api_url_edit.setText(config.get("api_url", "https://api.deepseek.com/v1/chat/completions"))
                self.api_key_edit.setText(config.get("api_key", ""))
                self.model_edit.setText(config.get("model", "deepseek-chat"))
                self.interval_spin.setValue(config.get("request_interval", 2.0))
                
                # 加载字幕样式设置
                style = config.get("style", {})
                if style.get("cn_font"):
                    self.cn_font_combo.setCurrentFont(QFont(style["cn_font"]))
                if style.get("cn_size"):
                    self.cn_size_spin.setValue(style["cn_size"])
                if style.get("cn_color"):
                    idx = self.cn_color_combo.findText(style["cn_color"])
                    if idx >= 0:
                        self.cn_color_combo.setCurrentIndex(idx)
                if style.get("en_font"):
                    self.en_font_combo.setCurrentFont(QFont(style["en_font"]))
                if style.get("en_size"):
                    self.en_size_spin.setValue(style["en_size"])
                if style.get("en_color"):
                    idx = self.en_color_combo.findText(style["en_color"])
                    if idx >= 0:
                        self.en_color_combo.setCurrentIndex(idx)
            except Exception as e:
                self.log(f"加载设置失败: {e}")
    
    def save_settings(self):
        all_config = {}
        if os.path.exists(self.CONFIG_FILE):
            try:
                with open(self.CONFIG_FILE, 'r', encoding='utf-8') as f:
                    all_config = json.load(f)
            except:
                pass
        
        all_config[self.CONFIG_KEY] = {
            "engine_index": self.engine_combo.currentIndex(),
            "api_url": self.api_url_edit.text(),
            "api_key": self.api_key_edit.text(),
            "model": self.model_edit.text(),
            "request_interval": self.interval_spin.value(),
            "style": {
                "cn_font": self.cn_font_combo.currentFont().family(),
                "cn_size": self.cn_size_spin.value(),
                "cn_color": self.cn_color_combo.currentText(),
                "en_font": self.en_font_combo.currentFont().family(),
                "en_size": self.en_size_spin.value(),
                "en_color": self.en_color_combo.currentText()
            }
        }
        
        try:
            with open(self.CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(all_config, f, indent=4, ensure_ascii=False)
        except Exception as e:
            self.log(f"保存设置失败: {e}")
    
    def on_prompt_changed(self, index):
        if index == 0:
            self.prompt_preview.clear()
            self.prompt_preview.setPlaceholderText("使用默认 Prompt (根据目标语言自动生成)")
        else:
            filename = self.prompt_combo.currentText()
            filepath = os.path.join(self.prompt_dir, filename)
            if os.path.exists(filepath):
                with open(filepath, 'r', encoding='utf-8') as f:
                    self.prompt_preview.setPlainText(f.read())
    
    def on_style_changed(self):
        """样式变化时更新预览并保存"""
        self.update_preview()
        self.save_settings()
    
    def update_preview(self):
        cn_color_map = {"白色": "#FFFFFF", "黄色": "#FFFF00", "青色": "#00FFFF", "绿色": "#00FF00"}
        en_color_map = {"白色": "#FFFFFF", "浅灰": "#CCCCCC", "黄色": "#FFFF00", "青色": "#00FFFF"}
        
        cn_color = cn_color_map.get(self.cn_color_combo.currentText(), "#FFFFFF")
        en_color = en_color_map.get(self.en_color_combo.currentText(), "#CCCCCC")
        
        self.preview_widget.set_cn_style(
            self.cn_font_combo.currentFont().family(),
            self.cn_size_spin.value(),
            cn_color
        )
        self.preview_widget.set_en_style(
            self.en_font_combo.currentFont().family(),
            self.en_size_spin.value(),
            en_color
        )
    
    def get_style_config(self):
        cn_color_map = {"白色": "&H00FFFFFF", "黄色": "&H0000FFFF", "青色": "&H00FFFF00", "绿色": "&H0000FF00"}
        en_color_map = {"白色": "&H00FFFFFF", "浅灰": "&H00CCCCCC", "黄色": "&H0000FFFF", "青色": "&H00FFFF00"}
        
        return {
            "cn_font": self.cn_font_combo.currentFont().family(),
            "cn_size": self.cn_size_spin.value(),
            "cn_color": cn_color_map.get(self.cn_color_combo.currentText(), "&H00FFFFFF"),
            "en_font": self.en_font_combo.currentFont().family(),
            "en_size": self.en_size_spin.value(),
            "en_color": en_color_map.get(self.en_color_combo.currentText(), "&H00CCCCCC"),
        }

    def browse_input(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择字幕文件", "", 
            "字幕文件 (*.srt);;所有文件 (*.*)"
        )
        if file_path:
            self.input_edit.setText(file_path)
    
    def _init_manager(self):
        if self.manager is None:
            from video_tool.core.subtitle_manager import SubtitleManager
            self.manager = SubtitleManager()
        
        engine_index = self.engine_combo.currentIndex()
        # 0: Deepseek, 1: 美团LongCat, 2: OpenRouter, 3: DeepLX, 4: 自定义
        engine_type = ["deepseek", "longcat", "openrouter", "deeplx", "custom"][engine_index]
        
        self.manager.set_engine(
            engine_type,
            self.api_key_edit.text().strip(),
            self.api_url_edit.text().strip(),
            self.model_edit.text().strip()
        )
    
    def test_connection(self):
        self.test_connection_btn.setEnabled(False)
        self.connection_status.setText("测试中...")
        self.connection_status.setStyleSheet("color: orange;")
        
        try:
            self._init_manager()
            test_text = ["Hello"]
            lang_code = "zh"
            
            self.log("正在测试 API 连接...")
            
            if self.manager.engine_type == "deeplx":
                result = self.manager._translate_deeplx(test_text, lang_code)
            else:
                result = self.manager._translate_batch(test_text, lang_code, None)
            
            if result and len(result) > 0:
                self.connection_status.setText("✓ 连接成功")
                self.connection_status.setStyleSheet("color: green;")
                self.log(f"连接测试成功! 测试翻译: '{test_text[0]}' -> '{result[0]}'")
            else:
                self.connection_status.setText("✗ 连接失败")
                self.connection_status.setStyleSheet("color: red;")
                self.log("连接测试失败: 返回结果为空")
                
        except Exception as e:
            self.connection_status.setText("✗ 连接失败")
            self.connection_status.setStyleSheet("color: red;")
            self.log(f"连接测试失败: {e}")
        
        finally:
            self.test_connection_btn.setEnabled(True)

    def translate_and_save(self):
        file_path = self.input_edit.text()
        if not file_path or not os.path.exists(file_path):
            self.log("错误: 请选择有效的字幕文件")
            return
        
        engine_index = self.engine_combo.currentIndex()
        api_key = self.api_key_edit.text().strip()
        if engine_index != 1 and not api_key:
            self.log("错误: 请输入 API Key")
            return
        
        if self.connection_status.text() not in ["✓ 连接成功"]:
            self.log("警告: 未测试连接或连接失败，建议先点击'测试连接'按钮")
            self.log("继续执行翻译...")
        
        try:
            self._init_manager()
            thread_count = int(self.thread_count_combo.currentText())
            request_interval = self.interval_spin.value()
            self.manager.set_thread_count(thread_count)
            self.manager.set_request_interval(request_interval)
            
            self.log(f"加载字幕文件: {file_path}")
            self.current_subtitles = self.manager.parse_srt(file_path)
            self.log(f"已加载 {len(self.current_subtitles)} 条字幕")
        except Exception as e:
            self.log(f"加载失败: {e}")
            return
        
        lang_text = self.lang_combo.currentText()
        lang_code = lang_text.split('(')[1].replace(')', '').strip() if '(' in lang_text else "zh"
        
        prompt_text = self.prompt_preview.toPlainText().strip() or None
        
        self.translate_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        
        engine_name = self.engine_combo.currentText()
        request_interval = self.interval_spin.value()
        thread_count = int(self.thread_count_combo.currentText())
        self.log(f"使用引擎: {engine_name}")
        self.log(f"目标语言: {lang_text}")
        self.log(f"并发数: {thread_count}")
        if request_interval > 0:
            self.log(f"请求间隔: {request_interval} 秒")
        
        self.translate_thread = TranslateThread(
            self.manager, 
            self.current_subtitles, 
            lang_code, 
            prompt_text,
            file_path
        )
        self.translate_thread.progress.connect(self.on_translate_progress)
        self.translate_thread.finished.connect(lambda t, o: self.on_translate_finished(t, o, file_path, lang_code))
        self.translate_thread.error.connect(self.on_translate_error)
        self.translate_thread.log.connect(self.log)
        self.translate_thread.start()
    
    def on_translate_progress(self, current, total):
        percent = int(current / total * 100)
        self.progress_bar.setValue(percent)
        if current % 10 == 0 or current == total:
            self.log(f"翻译进度: {current}/{total} ({percent}%)")
    
    def on_translate_finished(self, translated_subs, original_subs, source_path, lang_code):
        self.translate_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        
        self.log("翻译完成，正在验证结果...")
        
        untranslated_count = 0
        for i, (trans, orig) in enumerate(zip(translated_subs, original_subs)):
            if trans['text'] == orig['text'] and len(orig['text']) > 10:
                untranslated_count += 1
                if untranslated_count <= 5:
                    self.log(f"  第 {i+1} 条可能未翻译: {orig['text'][:50]}...")
        
        if untranslated_count > 0:
            self.log(f"警告: 发现 {untranslated_count} 条字幕可能未翻译（与原文相同）")
            self.log("建议: 降低并发数或检查 API 配额")
        else:
            self.log("✓ 所有字幕已成功翻译")
        
        self.log("\n开始保存文件...")
        
        base_path = os.path.splitext(source_path)[0]
        lang_suffix_map = {"zh": "chs", "ja": "jpn", "ko": "kor", "en": "eng"}
        lang_suffix = lang_suffix_map.get(lang_code, lang_code)
        
        translated_path = f"{base_path}.{lang_suffix}.srt"
        try:
            self.manager.save_srt(translated_subs, translated_path)
            self.log(f"✓ 已保存翻译字幕: {translated_path}")
        except Exception as e:
            self.log(f"✗ 保存翻译字幕失败: {e}")
        
        original_path = f"{base_path}.eng.srt"
        try:
            self.manager.save_srt(original_subs, original_path)
            self.log(f"✓ 已保存原文字幕: {original_path}")
        except Exception as e:
            self.log(f"✗ 保存原文字幕失败: {e}")
        
        bilingual_path = f"{base_path}.{lang_suffix}_eng.ass"
        try:
            bilingual_subs = self.manager.merge_subtitles(translated_subs, original_subs)
            self.save_ass(bilingual_subs, bilingual_path)
            self.log(f"✓ 已保存双语字幕: {bilingual_path}")
        except Exception as e:
            self.log(f"✗ 保存双语字幕失败: {e}")
        
        self.log("=" * 50)
        self.log("全部完成!")
        
        if untranslated_count > 0:
            self.log(f"\n提示: 如需重新翻译未成功的部分，可以降低并发数后重试")
    
    def on_translate_error(self, error_msg):
        self.translate_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.log(f"翻译失败: {error_msg}")

    def save_ass(self, subtitles, output_path):
        """保存字幕为 ASS 格式"""
        def srt_time_to_ass(srt_time):
            parts = srt_time.replace(',', '.').split(':')
            h = int(parts[0])
            m = parts[1]
            s_ms = parts[2]
            s, ms = s_ms.split('.')
            ms = ms[:2]
            return f"{h}:{m}:{s}.{ms}"
        
        style = self.get_style_config()
        
        ass_content = f"""[Script Info]
Title: Bilingual Subtitles
ScriptType: v4.00+
Collisions: Normal
PlayDepth: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default_CN,{style['cn_font']},{style['cn_size']},{style['cn_color']},&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,2,1,2,10,10,15,1
Style: Default_EN,{style['en_font']},{style['en_size']},{style['en_color']},&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,1,0,2,10,10,5,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        
        for sub in subtitles:
            time_range = sub['time_range']
            times = time_range.split(' --> ')
            if len(times) == 2:
                start = srt_time_to_ass(times[0].strip())
                end = srt_time_to_ass(times[1].strip())
                text = sub['text'].replace('\n', '\\N')
                lines = text.split('\\N')
                if len(lines) >= 2:
                    cn_text = lines[0]
                    en_text = '\\N'.join(lines[1:])
                    ass_content += f"Dialogue: 0,{start},{end},Default_CN,,0,0,0,,{cn_text}\n"
                    ass_content += f"Dialogue: 0,{start},{end},Default_EN,,0,0,0,,{en_text}\n"
                else:
                    ass_content += f"Dialogue: 0,{start},{end},Default_CN,,0,0,0,,{text}\n"
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(ass_content)

    def log(self, message):
        """输出日志到统一控制台"""
        console_info(message, "字幕处理")
