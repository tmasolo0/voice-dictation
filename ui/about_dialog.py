"""AboutDialog — диалог 'О программе'."""

from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton
from PyQt6.QtCore import Qt

from core.config_manager import BUNDLE_DIR


def _read_version() -> str:
    version_file = BUNDLE_DIR / "VERSION"
    if version_file.exists():
        return version_file.read_text(encoding='utf-8').strip()
    return "?"


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("О программе")
        self.setFixedSize(320, 180)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        version = _read_version()

        title = QLabel(f"<b>Voice Dictation v{version}</b>")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        dev = QLabel("Разработчик: Смирнов Дмитрий")
        dev.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(dev)

        email = QLabel('<a href="mailto:tmasolo0@gmail.com">tmasolo0@gmail.com</a>')
        email.setOpenExternalLinks(True)
        email.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(email)

        desc = QLabel("Голосовой ввод для Windows\nPush-to-talk, faster-whisper, LLM")
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(desc)

        layout.addStretch()

        ok_btn = QPushButton("OK")
        ok_btn.setFixedWidth(80)
        ok_btn.clicked.connect(self.accept)
        layout.addWidget(ok_btn, alignment=Qt.AlignmentFlag.AlignCenter)
