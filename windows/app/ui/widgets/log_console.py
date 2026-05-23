from PyQt5.QtWidgets import QTextEdit
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QTextCursor

from app.backend.parser import parse_parameter_line, is_table_separator


class LogConsole(QTextEdit):
    def __init__(self):
        super().__init__()
        self.setReadOnly(True)
        self.setObjectName("logConsole")
        self.document().setMaximumBlockCount(500)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)

    def append_log(self, ts: str, text: str):
        color = self._color_for_line(text)
        html = f'<span style="color:#888;">{ts}</span> '
        html += f'<span style="color:{color};">{self._escape(text)}</span><br>'

        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertHtml(html)

        sb = self.verticalScrollBar()
        if sb.maximum() - sb.value() < 40:
            sb.setValue(sb.maximum())

    def _color_for_line(self, text: str) -> str:
        if parse_parameter_line(text) is not None:
            return "#2ed573"
        if is_table_separator(text):
            return "#74b9ff"
        if '[tuning]' in text.lower():
            return "#ffa502"
        if 'error' in text.lower():
            return "#ff4757"
        if '>>> sent' in text.lower():
            return "#a29bfe"
        return "#dfe6e9"

    def _escape(self, text: str) -> str:
        return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
