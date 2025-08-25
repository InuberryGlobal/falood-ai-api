import sys
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout,
    QScrollArea, QTextEdit
)
from PyQt5.QtCore import Qt, QPoint
from PyQt5.QtGui import QTextCursor

class StealthOverlay(QWidget):
    def __init__(self):
        if QApplication.instance() is None:
            self.app = QApplication(sys.argv)
        else:
            self.app = QApplication.instance()

        super().__init__()

        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint 
        )
        self.setAttribute(Qt.WA_TranslucentBackground)

        self.setStyleSheet("""
            QWidget {
                background-color: rgba(30, 30, 30, 220);
                color: white;
                font-size: 16px;
                padding: 10px;
            }
            QTextEdit {
                background-color: transparent;
                border: none;
                color: white;
                font-size: 16px;
            }
        """)

        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)

        self.text_area = QTextEdit()
        self.text_area.setReadOnly(True)
        self.text_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.text_area)
        scroll.setFrameShape(QScrollArea.NoFrame)

        layout.addWidget(scroll)
        self.setLayout(layout)
        self.resize(600, 800)
        self.move(100, 100)

        self.drag_position = None

    def update_text(self, text: str):
        self.text_area.append(text)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_position = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton and self.drag_position is not None:
            self.move(event.globalPos() - self.drag_position)
            event.accept()

    def update_text(self, text: str):
        cursor = self.text_area.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.text_area.setTextCursor(cursor)
        self.text_area.insertPlainText(text)
        self.text_area.ensureCursorVisible()

    def run(self):
        self.show()
        self.app.exec_()
