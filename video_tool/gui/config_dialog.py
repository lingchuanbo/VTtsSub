from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, 
                             QPushButton, QFileDialog, QFormLayout)
import json
import os

CONFIG_FILE = "config.json"

class ConfigDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configuration")
        self.resize(400, 200)
        self.layout = QVBoxLayout(self)
        
        self.form_layout = QFormLayout()
        
        self.ffmpeg_path_edit = QLineEdit()
        self.browse_ffmpeg_btn = QPushButton("Browse")
        self.browse_ffmpeg_btn.clicked.connect(self.browse_ffmpeg)
        
        ffmpeg_layout = QHBoxLayout()
        ffmpeg_layout.addWidget(self.ffmpeg_path_edit)
        ffmpeg_layout.addWidget(self.browse_ffmpeg_btn)
        
        self.form_layout.addRow("FFmpeg Path:", ffmpeg_layout)
        
        # ElevenLabs API Key
        self.elevenlabs_key_edit = QLineEdit()
        self.elevenlabs_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.elevenlabs_key_edit.setPlaceholderText("可选，用于 TTS 功能")
        self.form_layout.addRow("ElevenLabs API Key:", self.elevenlabs_key_edit)
        
        self.layout.addLayout(self.form_layout)
        
        self.buttons = QHBoxLayout()
        self.save_btn = QPushButton("Save")
        self.save_btn.clicked.connect(self.save_config)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        
        self.buttons.addWidget(self.save_btn)
        self.buttons.addWidget(self.cancel_btn)
        self.layout.addLayout(self.buttons)
        
        self.load_config()

    def browse_ffmpeg(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select FFmpeg Executable", "", "Executables (*.exe);;All Files (*)")
        if path:
            self.ffmpeg_path_edit.setText(path)

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f:
                    config = json.load(f)
                    self.ffmpeg_path_edit.setText(config.get("ffmpeg_path", "ffmpeg"))
                    self.elevenlabs_key_edit.setText(config.get("elevenlabs_api_key", ""))
            except Exception as e:
                print(f"Error loading config: {e}")
        else:
             self.ffmpeg_path_edit.setText("ffmpeg")

    def save_config(self):
        config = {
            "ffmpeg_path": self.ffmpeg_path_edit.text(),
            "elevenlabs_api_key": self.elevenlabs_key_edit.text()
        }
        try:
            with open(CONFIG_FILE, 'w') as f:
                json.dump(config, f, indent=4)
            self.accept()
        except Exception as e:
            print(f"Error saving config: {e}")

