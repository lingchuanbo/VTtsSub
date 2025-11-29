
MODERN_DARK_THEME = """
/* Global Styles */
QMainWindow {
    background-color: #1e1e2e;
    color: #cdd6f4;
}

QWidget {
    background-color: #1e1e2e;
    color: #cdd6f4;
    font-family: "Segoe UI", "Helvetica Neue", sans-serif;
    font-size: 14px;
}

/* Sidebar Styles */
QFrame#sidebar {
    background-color: #181825;
    border-right: 1px solid #313244;
}

QPushButton#nav_btn {
    background-color: transparent;
    color: #a6adc8;
    border: none;
    text-align: left;
    padding: 12px 20px;
    font-size: 15px;
    border-radius: 8px;
    margin: 4px 8px;
}

QPushButton#nav_btn:hover {
    background-color: #313244;
    color: #cdd6f4;
}

QPushButton#nav_btn:checked {
    background-color: #45475a;
    color: #89b4fa;
    font-weight: bold;
    border-left: 3px solid #89b4fa;
}

/* Content Area Styles */
QStackedWidget {
    background-color: #1e1e2e;
    border: none;
}

/* Common Widget Styles */
QLabel {
    color: #cdd6f4;
}

QLineEdit, QTextEdit, QPlainTextEdit {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 4px;
    padding: 6px;
    selection-background-color: #585b70;
}

QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
    border: 1px solid #89b4fa;
}

QPushButton {
    background-color: #89b4fa;
    color: #1e1e2e;
    border: none;
    border-radius: 4px;
    padding: 8px 16px;
    font-weight: bold;
}

QPushButton:hover {
    background-color: #b4befe;
}

QPushButton:pressed {
    background-color: #74c7ec;
}

QPushButton:disabled {
    background-color: #45475a;
    color: #6c7086;
}

/* GroupBox Styles */
QGroupBox {
    border: 1px solid #45475a;
    border-radius: 6px;
    margin-top: 12px;
    padding-top: 10px;
    font-weight: bold;
    color: #89b4fa;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 5px;
    left: 10px;
}

/* ScrollBar Styles */
QScrollBar:vertical {
    border: none;
    background: #181825;
    width: 10px;
    margin: 0px;
}

QScrollBar::handle:vertical {
    background: #45475a;
    min-height: 20px;
    border-radius: 5px;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

QScrollBar:horizontal {
    border: none;
    background: #181825;
    height: 10px;
    margin: 0px;
}

QScrollBar::handle:horizontal {
    background: #45475a;
    min-width: 20px;
    border-radius: 5px;
}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
}

/* TabWidget Styles (if used elsewhere) */
QTabWidget::pane {
    border: 1px solid #45475a;
    background-color: #1e1e2e;
}

QTabBar::tab {
    background-color: #181825;
    color: #a6adc8;
    padding: 8px 16px;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
}

QTabBar::tab:selected {
    background-color: #1e1e2e;
    color: #89b4fa;
    border-bottom: 2px solid #89b4fa;
}

/* Menu Bar */
QMenuBar {
    background-color: #181825;
    color: #cdd6f4;
}

QMenuBar::item {
    background-color: transparent;
    padding: 8px 12px;
}

QMenuBar::item:selected {
    background-color: #313244;
}

QMenu {
    background-color: #181825;
    color: #cdd6f4;
    border: 1px solid #313244;
}

QMenu::item {
    padding: 6px 24px;
}

QMenu::item:selected {
    background-color: #313244;
}
"""
