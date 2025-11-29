from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QTextEdit, QHBoxLayout, 
                             QPushButton, QComboBox, QLabel, QMainWindow)
from PyQt6.QtCore import pyqtSignal, QObject, Qt
from PyQt6.QtGui import QTextCursor, QColor, QCloseEvent
from datetime import datetime


class LogLevel:
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class ConsoleHandler(QObject):
    """全局控制台日志处理器"""
    log_signal = pyqtSignal(str, str, str)  # message, level, source
    
    _instance = None
    
    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = ConsoleHandler()
        return cls._instance
    
    def log(self, message, level=LogLevel.INFO, source="System"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_signal.emit(f"[{timestamp}] [{source}] {message}", level, source)
    
    def debug(self, message, source="System"):
        self.log(message, LogLevel.DEBUG, source)
    
    def info(self, message, source="System"):
        self.log(message, LogLevel.INFO, source)
    
    def warning(self, message, source="System"):
        self.log(message, LogLevel.WARNING, source)
    
    def error(self, message, source="System"):
        self.log(message, LogLevel.ERROR, source)


class ConsoleWidget(QWidget):
    """统一控制台组件"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()
        self.connect_handler()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # 工具栏
        toolbar = QHBoxLayout()
        
        # 日志级别过滤
        toolbar.addWidget(QLabel("过滤:"))
        self.level_filter = QComboBox()
        self.level_filter.addItems(["全部", "DEBUG", "INFO", "WARNING", "ERROR"])
        self.level_filter.currentTextChanged.connect(self.apply_filter)
        toolbar.addWidget(self.level_filter)
        
        # 来源过滤
        toolbar.addWidget(QLabel("来源:"))
        self.source_filter = QComboBox()
        self.source_filter.addItem("全部")
        self.source_filter.currentTextChanged.connect(self.apply_filter)
        toolbar.addWidget(self.source_filter)
        
        toolbar.addStretch()
        
        # 清空按钮
        self.clear_btn = QPushButton("清空")
        self.clear_btn.clicked.connect(self.clear_console)
        toolbar.addWidget(self.clear_btn)
        
        layout.addLayout(toolbar)
        
        # 日志显示区域
        self.console_text = QTextEdit()
        self.console_text.setReadOnly(True)
        self.console_text.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #d4d4d4;
                font-family: Consolas, 'Courier New', monospace;
                font-size: 12px;
            }
        """)
        layout.addWidget(self.console_text)
        
        # 存储所有日志用于过滤
        self.all_logs = []
        self.sources = set()
    
    def connect_handler(self):
        ConsoleHandler.instance().log_signal.connect(self.append_log)
    
    def append_log(self, message, level, source):
        """添加日志"""
        self.all_logs.append((message, level, source))
        
        # 更新来源过滤器
        if source not in self.sources:
            self.sources.add(source)
            self.source_filter.addItem(source)
        
        # 检查是否符合当前过滤条件
        if self.should_show(level, source):
            self.display_log(message, level)
    
    def should_show(self, level, source):
        """检查是否应该显示该日志"""
        level_filter = self.level_filter.currentText()
        source_filter = self.source_filter.currentText()
        
        if level_filter != "全部" and level != level_filter:
            return False
        if source_filter != "全部" and source != source_filter:
            return False
        return True
    
    def display_log(self, message, level):
        """显示日志到控制台"""
        color_map = {
            LogLevel.DEBUG: "#808080",
            LogLevel.INFO: "#d4d4d4",
            LogLevel.WARNING: "#dcdcaa",
            LogLevel.ERROR: "#f14c4c"
        }
        color = color_map.get(level, "#d4d4d4")
        
        cursor = self.console_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        
        html = f'<span style="color: {color};">{message}</span><br>'
        cursor.insertHtml(html)
        
        # 滚动到底部
        self.console_text.verticalScrollBar().setValue(
            self.console_text.verticalScrollBar().maximum()
        )
    
    def apply_filter(self):
        """应用过滤器"""
        self.console_text.clear()
        for message, level, source in self.all_logs:
            if self.should_show(level, source):
                self.display_log(message, level)
    
    def clear_console(self):
        """清空控制台"""
        self.console_text.clear()
        self.all_logs.clear()


class ConsoleWindow(QMainWindow):
    """独立控制台窗口"""
    closed = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("控制台")
        self.resize(800, 400)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.Tool)
        
        self.console_widget = ConsoleWidget()
        self.setCentralWidget(self.console_widget)
    
    def closeEvent(self, event: QCloseEvent):
        self.closed.emit()
        event.accept()


# 便捷函数
def console_log(message, level=LogLevel.INFO, source="System"):
    ConsoleHandler.instance().log(message, level, source)

def console_debug(message, source="System"):
    ConsoleHandler.instance().debug(message, source)

def console_info(message, source="System"):
    ConsoleHandler.instance().info(message, source)

def console_warning(message, source="System"):
    ConsoleHandler.instance().warning(message, source)

def console_error(message, source="System"):
    ConsoleHandler.instance().error(message, source)
