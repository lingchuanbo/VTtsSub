
# 通用字体设置
FONT_FAMILY = '"Microsoft YaHei", "微软雅黑", "Segoe UI", "Helvetica Neue", sans-serif'

# 主题配置
THEMES = {
    "dark": "深色主题",
    "light": "浅色主题",
    "blue": "蓝色主题",
    "green": "绿色主题",
}

def get_theme_style(theme_name: str) -> str:
    """获取指定主题的样式表"""
    if theme_name == "light":
        return LIGHT_THEME
    elif theme_name == "blue":
        return BLUE_THEME
    elif theme_name == "green":
        return GREEN_THEME
    else:
        return DARK_THEME

# 深色主题 (默认)
DARK_THEME = f"""
/* Global Styles */
QMainWindow {{
    background-color: #1e1e2e;
    color: #cdd6f4;
}}

QWidget {{
    background-color: #1e1e2e;
    color: #cdd6f4;
    font-family: {FONT_FAMILY};
    font-size: 14px;
}}

QFrame#sidebar {{
    background-color: #181825;
    border-right: 1px solid #313244;
}}

QPushButton#nav_btn {{
    background-color: transparent;
    color: #a6adc8;
    border: none;
    text-align: left;
    padding: 12px 20px;
    font-size: 15px;
    border-radius: 8px;
    margin: 4px 8px;
}}

QPushButton#nav_btn:hover {{
    background-color: #313244;
    color: #cdd6f4;
}}

QPushButton#nav_btn:checked {{
    background-color: #45475a;
    color: #89b4fa;
    font-weight: bold;
    border-left: 3px solid #89b4fa;
}}

QStackedWidget {{
    background-color: #1e1e2e;
    border: none;
}}

QLabel {{
    color: #cdd6f4;
}}

QLineEdit, QTextEdit, QPlainTextEdit {{
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 4px;
    padding: 6px;
    selection-background-color: #585b70;
}}

QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
    border: 1px solid #89b4fa;
}}

QPushButton {{
    background-color: #89b4fa;
    color: #1e1e2e;
    border: none;
    border-radius: 4px;
    padding: 8px 16px;
    font-weight: bold;
}}

QPushButton:hover {{
    background-color: #b4befe;
}}

QPushButton:pressed {{
    background-color: #74c7ec;
}}

QPushButton:disabled {{
    background-color: #45475a;
    color: #6c7086;
}}

QGroupBox {{
    border: 1px solid #45475a;
    border-radius: 6px;
    margin-top: 12px;
    padding-top: 10px;
    font-weight: bold;
    color: #89b4fa;
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 5px;
    left: 10px;
}}

QScrollBar:vertical {{
    border: none;
    background: #181825;
    width: 10px;
    margin: 0px;
}}

QScrollBar::handle:vertical {{
    background: #45475a;
    min-height: 20px;
    border-radius: 5px;
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}

QScrollBar:horizontal {{
    border: none;
    background: #181825;
    height: 10px;
    margin: 0px;
}}

QScrollBar::handle:horizontal {{
    background: #45475a;
    min-width: 20px;
    border-radius: 5px;
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
}}

QTabWidget::pane {{
    border: 1px solid #45475a;
    background-color: #1e1e2e;
}}

QTabBar::tab {{
    background-color: #181825;
    color: #a6adc8;
    padding: 8px 16px;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
}}

QTabBar::tab:selected {{
    background-color: #1e1e2e;
    color: #89b4fa;
    border-bottom: 2px solid #89b4fa;
}}

QMenuBar {{
    background-color: #181825;
    color: #cdd6f4;
}}

QMenuBar::item {{
    background-color: transparent;
    padding: 8px 12px;
}}

QMenuBar::item:selected {{
    background-color: #313244;
}}

QMenu {{
    background-color: #181825;
    color: #cdd6f4;
    border: 1px solid #313244;
}}

QMenu::item {{
    padding: 6px 24px;
}}

QMenu::item:selected {{
    background-color: #313244;
}}

QComboBox {{
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 4px;
    padding: 6px;
}}

QComboBox:hover {{
    border: 1px solid #89b4fa;
}}

QComboBox::drop-down {{
    border: none;
}}

QComboBox QAbstractItemView {{
    background-color: #313244;
    color: #cdd6f4;
    selection-background-color: #45475a;
}}

QSpinBox, QDoubleSpinBox {{
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 4px;
    padding: 6px;
}}

QCheckBox {{
    color: #cdd6f4;
}}

QCheckBox::indicator {{
    width: 18px;
    height: 18px;
}}

QProgressBar {{
    background-color: #313244;
    border: none;
    border-radius: 4px;
    text-align: center;
    color: #cdd6f4;
}}

QProgressBar::chunk {{
    background-color: #89b4fa;
    border-radius: 4px;
}}
"""

# 浅色主题
LIGHT_THEME = f"""
QMainWindow {{
    background-color: #f5f5f5;
    color: #333333;
}}

QWidget {{
    background-color: #f5f5f5;
    color: #333333;
    font-family: {FONT_FAMILY};
    font-size: 14px;
}}

QFrame#sidebar {{
    background-color: #e8e8e8;
    border-right: 1px solid #d0d0d0;
}}

QPushButton#nav_btn {{
    background-color: transparent;
    color: #666666;
    border: none;
    text-align: left;
    padding: 12px 20px;
    font-size: 15px;
    border-radius: 8px;
    margin: 4px 8px;
}}

QPushButton#nav_btn:hover {{
    background-color: #d8d8d8;
    color: #333333;
}}

QPushButton#nav_btn:checked {{
    background-color: #c8c8c8;
    color: #1a73e8;
    font-weight: bold;
    border-left: 3px solid #1a73e8;
}}

QStackedWidget {{
    background-color: #f5f5f5;
    border: none;
}}

QLabel {{
    color: #333333;
}}

QLineEdit, QTextEdit, QPlainTextEdit {{
    background-color: #ffffff;
    color: #333333;
    border: 1px solid #d0d0d0;
    border-radius: 4px;
    padding: 6px;
    selection-background-color: #b3d4fc;
}}

QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
    border: 1px solid #1a73e8;
}}

QPushButton {{
    background-color: #1a73e8;
    color: #ffffff;
    border: none;
    border-radius: 4px;
    padding: 8px 16px;
    font-weight: bold;
}}

QPushButton:hover {{
    background-color: #1557b0;
}}

QPushButton:pressed {{
    background-color: #0d47a1;
}}

QPushButton:disabled {{
    background-color: #d0d0d0;
    color: #999999;
}}

QGroupBox {{
    border: 1px solid #d0d0d0;
    border-radius: 6px;
    margin-top: 12px;
    padding-top: 10px;
    font-weight: bold;
    color: #1a73e8;
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 5px;
    left: 10px;
}}

QScrollBar:vertical {{
    border: none;
    background: #e8e8e8;
    width: 10px;
}}

QScrollBar::handle:vertical {{
    background: #c0c0c0;
    min-height: 20px;
    border-radius: 5px;
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}

QScrollBar:horizontal {{
    border: none;
    background: #e8e8e8;
    height: 10px;
}}

QScrollBar::handle:horizontal {{
    background: #c0c0c0;
    min-width: 20px;
    border-radius: 5px;
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
}}

QMenuBar {{
    background-color: #e8e8e8;
    color: #333333;
}}

QMenuBar::item {{
    background-color: transparent;
    padding: 8px 12px;
}}

QMenuBar::item:selected {{
    background-color: #d0d0d0;
}}

QMenu {{
    background-color: #ffffff;
    color: #333333;
    border: 1px solid #d0d0d0;
}}

QMenu::item {{
    padding: 6px 24px;
}}

QMenu::item:selected {{
    background-color: #e8e8e8;
}}

QComboBox {{
    background-color: #ffffff;
    color: #333333;
    border: 1px solid #d0d0d0;
    border-radius: 4px;
    padding: 6px;
}}

QComboBox:hover {{
    border: 1px solid #1a73e8;
}}

QComboBox::drop-down {{
    border: none;
}}

QComboBox QAbstractItemView {{
    background-color: #ffffff;
    color: #333333;
    selection-background-color: #e8e8e8;
}}

QSpinBox, QDoubleSpinBox {{
    background-color: #ffffff;
    color: #333333;
    border: 1px solid #d0d0d0;
    border-radius: 4px;
    padding: 6px;
}}

QCheckBox {{
    color: #333333;
}}

QProgressBar {{
    background-color: #e0e0e0;
    border: none;
    border-radius: 4px;
    text-align: center;
    color: #333333;
}}

QProgressBar::chunk {{
    background-color: #1a73e8;
    border-radius: 4px;
}}
"""

# 蓝色主题
BLUE_THEME = f"""
QMainWindow {{
    background-color: #0a1929;
    color: #b2bac2;
}}

QWidget {{
    background-color: #0a1929;
    color: #b2bac2;
    font-family: {FONT_FAMILY};
    font-size: 14px;
}}

QFrame#sidebar {{
    background-color: #001e3c;
    border-right: 1px solid #132f4c;
}}

QPushButton#nav_btn {{
    background-color: transparent;
    color: #8796a5;
    border: none;
    text-align: left;
    padding: 12px 20px;
    font-size: 15px;
    border-radius: 8px;
    margin: 4px 8px;
}}

QPushButton#nav_btn:hover {{
    background-color: #132f4c;
    color: #b2bac2;
}}

QPushButton#nav_btn:checked {{
    background-color: #173a5e;
    color: #66b2ff;
    font-weight: bold;
    border-left: 3px solid #66b2ff;
}}

QStackedWidget {{
    background-color: #0a1929;
    border: none;
}}

QLabel {{
    color: #b2bac2;
}}

QLineEdit, QTextEdit, QPlainTextEdit {{
    background-color: #132f4c;
    color: #b2bac2;
    border: 1px solid #1e4976;
    border-radius: 4px;
    padding: 6px;
    selection-background-color: #265d97;
}}

QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
    border: 1px solid #66b2ff;
}}

QPushButton {{
    background-color: #0072e5;
    color: #ffffff;
    border: none;
    border-radius: 4px;
    padding: 8px 16px;
    font-weight: bold;
}}

QPushButton:hover {{
    background-color: #0059b2;
}}

QPushButton:pressed {{
    background-color: #004c99;
}}

QPushButton:disabled {{
    background-color: #173a5e;
    color: #5c6b7a;
}}

QGroupBox {{
    border: 1px solid #1e4976;
    border-radius: 6px;
    margin-top: 12px;
    padding-top: 10px;
    font-weight: bold;
    color: #66b2ff;
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 5px;
    left: 10px;
}}

QScrollBar:vertical {{
    border: none;
    background: #001e3c;
    width: 10px;
}}

QScrollBar::handle:vertical {{
    background: #1e4976;
    min-height: 20px;
    border-radius: 5px;
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}

QScrollBar:horizontal {{
    border: none;
    background: #001e3c;
    height: 10px;
}}

QScrollBar::handle:horizontal {{
    background: #1e4976;
    min-width: 20px;
    border-radius: 5px;
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
}}

QMenuBar {{
    background-color: #001e3c;
    color: #b2bac2;
}}

QMenuBar::item {{
    background-color: transparent;
    padding: 8px 12px;
}}

QMenuBar::item:selected {{
    background-color: #132f4c;
}}

QMenu {{
    background-color: #001e3c;
    color: #b2bac2;
    border: 1px solid #132f4c;
}}

QMenu::item {{
    padding: 6px 24px;
}}

QMenu::item:selected {{
    background-color: #132f4c;
}}

QComboBox {{
    background-color: #132f4c;
    color: #b2bac2;
    border: 1px solid #1e4976;
    border-radius: 4px;
    padding: 6px;
}}

QComboBox:hover {{
    border: 1px solid #66b2ff;
}}

QComboBox::drop-down {{
    border: none;
}}

QComboBox QAbstractItemView {{
    background-color: #132f4c;
    color: #b2bac2;
    selection-background-color: #173a5e;
}}

QSpinBox, QDoubleSpinBox {{
    background-color: #132f4c;
    color: #b2bac2;
    border: 1px solid #1e4976;
    border-radius: 4px;
    padding: 6px;
}}

QCheckBox {{
    color: #b2bac2;
}}

QProgressBar {{
    background-color: #132f4c;
    border: none;
    border-radius: 4px;
    text-align: center;
    color: #b2bac2;
}}

QProgressBar::chunk {{
    background-color: #0072e5;
    border-radius: 4px;
}}
"""

# 绿色主题
GREEN_THEME = f"""
QMainWindow {{
    background-color: #1a2f1a;
    color: #c8e6c9;
}}

QWidget {{
    background-color: #1a2f1a;
    color: #c8e6c9;
    font-family: {FONT_FAMILY};
    font-size: 14px;
}}

QFrame#sidebar {{
    background-color: #0d1f0d;
    border-right: 1px solid #2e5a2e;
}}

QPushButton#nav_btn {{
    background-color: transparent;
    color: #a5d6a7;
    border: none;
    text-align: left;
    padding: 12px 20px;
    font-size: 15px;
    border-radius: 8px;
    margin: 4px 8px;
}}

QPushButton#nav_btn:hover {{
    background-color: #2e5a2e;
    color: #c8e6c9;
}}

QPushButton#nav_btn:checked {{
    background-color: #3d7a3d;
    color: #81c784;
    font-weight: bold;
    border-left: 3px solid #81c784;
}}

QStackedWidget {{
    background-color: #1a2f1a;
    border: none;
}}

QLabel {{
    color: #c8e6c9;
}}

QLineEdit, QTextEdit, QPlainTextEdit {{
    background-color: #2e5a2e;
    color: #c8e6c9;
    border: 1px solid #3d7a3d;
    border-radius: 4px;
    padding: 6px;
    selection-background-color: #4caf50;
}}

QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
    border: 1px solid #81c784;
}}

QPushButton {{
    background-color: #4caf50;
    color: #1a2f1a;
    border: none;
    border-radius: 4px;
    padding: 8px 16px;
    font-weight: bold;
}}

QPushButton:hover {{
    background-color: #66bb6a;
}}

QPushButton:pressed {{
    background-color: #43a047;
}}

QPushButton:disabled {{
    background-color: #3d7a3d;
    color: #6b8e6b;
}}

QGroupBox {{
    border: 1px solid #3d7a3d;
    border-radius: 6px;
    margin-top: 12px;
    padding-top: 10px;
    font-weight: bold;
    color: #81c784;
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 5px;
    left: 10px;
}}

QScrollBar:vertical {{
    border: none;
    background: #0d1f0d;
    width: 10px;
}}

QScrollBar::handle:vertical {{
    background: #3d7a3d;
    min-height: 20px;
    border-radius: 5px;
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}

QScrollBar:horizontal {{
    border: none;
    background: #0d1f0d;
    height: 10px;
}}

QScrollBar::handle:horizontal {{
    background: #3d7a3d;
    min-width: 20px;
    border-radius: 5px;
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
}}

QMenuBar {{
    background-color: #0d1f0d;
    color: #c8e6c9;
}}

QMenuBar::item {{
    background-color: transparent;
    padding: 8px 12px;
}}

QMenuBar::item:selected {{
    background-color: #2e5a2e;
}}

QMenu {{
    background-color: #0d1f0d;
    color: #c8e6c9;
    border: 1px solid #2e5a2e;
}}

QMenu::item {{
    padding: 6px 24px;
}}

QMenu::item:selected {{
    background-color: #2e5a2e;
}}

QComboBox {{
    background-color: #2e5a2e;
    color: #c8e6c9;
    border: 1px solid #3d7a3d;
    border-radius: 4px;
    padding: 6px;
}}

QComboBox:hover {{
    border: 1px solid #81c784;
}}

QComboBox::drop-down {{
    border: none;
}}

QComboBox QAbstractItemView {{
    background-color: #2e5a2e;
    color: #c8e6c9;
    selection-background-color: #3d7a3d;
}}

QSpinBox, QDoubleSpinBox {{
    background-color: #2e5a2e;
    color: #c8e6c9;
    border: 1px solid #3d7a3d;
    border-radius: 4px;
    padding: 6px;
}}

QCheckBox {{
    color: #c8e6c9;
}}

QProgressBar {{
    background-color: #2e5a2e;
    border: none;
    border-radius: 4px;
    text-align: center;
    color: #c8e6c9;
}}

QProgressBar::chunk {{
    background-color: #4caf50;
    border-radius: 4px;
}}
"""

# 兼容旧代码
MODERN_DARK_THEME = DARK_THEME
