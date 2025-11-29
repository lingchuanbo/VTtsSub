import sys
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QMenuBar, QMenu, QMessageBox, QFrame, QPushButton, QStackedWidget,
                             QButtonGroup, QSizePolicy)
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtCore import Qt, QSize
from .config_dialog import ConfigDialog
from .widgets import (AudioExtractorWidget, ASRWidget, SubtitleWidget, 
                     TTSWidget, TranscoderWidget, VideoComposerWidget,
                     ConsoleWindow, console_info)
from .styles import MODERN_DARK_THEME

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Video Processing Tool")
        self.resize(1200, 800)

        # Main container
        self.main_widget = QWidget()
        self.setCentralWidget(self.main_widget)
        self.main_layout = QHBoxLayout(self.main_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # Sidebar
        self._create_sidebar()
        
        # Content Area
        self.content_stack = QStackedWidget()
        self.main_layout.addWidget(self.content_stack)
        
        # Independent Console Window
        self.console_window = ConsoleWindow(self)
        self.console_window.closed.connect(self._on_console_closed)
        
        self._create_actions()
        self._create_menu()
        self._init_widgets()
        
        # Select first item by default
        if self.nav_group.buttons():
            self.nav_group.buttons()[0].setChecked(True)
            self.content_stack.setCurrentIndex(0)

        console_info("应用程序已启动", "System")

    def _create_sidebar(self):
        self.sidebar = QFrame()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(250)
        
        self.sidebar_layout = QVBoxLayout(self.sidebar)
        self.sidebar_layout.setContentsMargins(10, 20, 10, 20)
        self.sidebar_layout.setSpacing(10)
        
        # Navigation Button Group
        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_group.buttonClicked.connect(self._on_nav_clicked)
        
        self.main_layout.addWidget(self.sidebar)
        
        # Add stretch to bottom of sidebar
        self.sidebar_layout.addStretch()

    def _add_nav_button(self, text, index):
        btn = QPushButton(text)
        btn.setObjectName("nav_btn")
        btn.setCheckable(True)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        
        # Insert before the stretch item (last item)
        self.sidebar_layout.insertWidget(self.sidebar_layout.count() - 1, btn)
        self.nav_group.addButton(btn, index)
        return btn

    def _init_widgets(self):
        # Define modules: (Name, Widget Instance)
        modules = [
            ("音频提取", AudioExtractorWidget()),
            ("语音识别 (ASR)", ASRWidget()),
            ("字幕处理", SubtitleWidget()),
            ("文字转语音 (TTS)", TTSWidget()),
            ("视频合成", VideoComposerWidget()),
            ("视频转码", TranscoderWidget())
        ]
        
        for i, (name, widget) in enumerate(modules):
            self.content_stack.addWidget(widget)
            self._add_nav_button(name, i)

    def _on_nav_clicked(self, btn):
        index = self.nav_group.id(btn)
        self.content_stack.setCurrentIndex(index)

    def _create_actions(self):
        self.config_action = QAction("配置", self)
        self.config_action.triggered.connect(self.open_config)
        
        self.console_action = QAction("控制台", self)
        self.console_action.setCheckable(True)
        self.console_action.setChecked(False)
        self.console_action.triggered.connect(self.toggle_console)
        
        self.exit_action = QAction("退出", self)
        self.exit_action.triggered.connect(self.close)

    def _create_menu(self):
        menu_bar = self.menuBar()
        
        # File Menu
        file_menu = menu_bar.addMenu("文件")
        file_menu.addAction(self.config_action)
        file_menu.addSeparator()
        file_menu.addAction(self.exit_action)
        
        # View Menu
        view_menu = menu_bar.addMenu("视图")
        view_menu.addAction(self.console_action)

    def open_config(self):
        dialog = ConfigDialog(self)
        dialog.exec()
    
    def toggle_console(self, checked):
        """切换控制台窗口显示/隐藏"""
        if checked:
            self.console_window.show()
            self.console_window.raise_()
            self.console_window.activateWindow()
        else:
            self.console_window.hide()
    
    def _on_console_closed(self):
        """控制台窗口关闭时更新菜单状态"""
        self.console_action.setChecked(False)
    
    def closeEvent(self, event):
        """主窗口关闭时也关闭控制台"""
        self.console_window.close()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet(MODERN_DARK_THEME)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
