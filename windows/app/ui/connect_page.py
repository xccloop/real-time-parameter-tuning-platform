from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QFrame, QSizePolicy
)
from PyQt5.QtCore import Qt, QTimer

from app.backend.tcp_client import TcpWorker
from app.backend.parser import AppState


_IP_HISTORY = ["10.163.14.121"]
_PORT_HISTORY = ["9000"]

_INPUT_STYLE = """
QLineEdit {
    padding: 10px 14px;
    font-size: 14px;
    border-radius: 6px;
}
"""


class ConnectPage(QWidget):
    def __init__(self, tcp_worker: TcpWorker, state: AppState):
        super().__init__()
        self.tcp_worker = tcp_worker
        self.state = state
        self._connecting = False

        self._setup_ui()

        self.tcp_worker.connection_changed.connect(self._on_connection_changed)
        self.tcp_worker.error_occurred.connect(self._on_error)

        self._timeout_timer = QTimer()
        self._timeout_timer.setSingleShot(True)
        self._timeout_timer.timeout.connect(self._on_connect_timeout)

    def _setup_ui(self):
        vbox = QVBoxLayout(self)
        vbox.setAlignment(Qt.AlignCenter)
        vbox.addStretch(2)

        # Title
        title = QLabel("连接板卡")
        title.setStyleSheet("font-size: 28px; font-weight: bold; color: #eceff1;")
        title.setAlignment(Qt.AlignCenter)
        vbox.addWidget(title)

        subtitle = QLabel("输入板卡 TCP 地址和端口建立连接")
        subtitle.setStyleSheet("font-size: 13px; color: #78909c; margin-bottom: 8px;")
        subtitle.setAlignment(Qt.AlignCenter)
        vbox.addWidget(subtitle)

        vbox.addSpacing(32)

        # Card
        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background: #252525;
                border-radius: 16px;
                padding: 24px;
            }
        """)
        card.setFixedWidth(400)
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(18)
        card_layout.setContentsMargins(28, 28, 28, 28)

        ip_label = QLabel("IP 地址")
        ip_label.setStyleSheet("font-size: 12px; color: #90a4ae; font-weight: 500;")
        card_layout.addWidget(ip_label)

        self.ip_input = QLineEdit()
        self.ip_input.setPlaceholderText("10.221.114.121")
        self.ip_input.setStyleSheet(_INPUT_STYLE)
        self.ip_input.setFixedHeight(44)
        if _IP_HISTORY:
            self.ip_input.setText(_IP_HISTORY[0])
        card_layout.addWidget(self.ip_input)

        port_label = QLabel("端口")
        port_label.setStyleSheet("font-size: 12px; color: #90a4ae; font-weight: 500;")
        card_layout.addWidget(port_label)

        self.port_input = QLineEdit()
        self.port_input.setPlaceholderText("9000")
        self.port_input.setStyleSheet(_INPUT_STYLE)
        self.port_input.setFixedHeight(44)
        self.port_input.setFixedWidth(120)
        if _PORT_HISTORY:
            self.port_input.setText(_PORT_HISTORY[0])
        card_layout.addWidget(self.port_input)

        card_layout.addSpacing(8)

        self.connect_btn = QPushButton("连接板卡")
        self.connect_btn.setStyleSheet("""
            QPushButton {
                padding: 12px;
                font-size: 15px;
                font-weight: bold;
            }
        """)
        self.connect_btn.setFixedHeight(48)
        self.connect_btn.setCursor(Qt.PointingHandCursor)
        self.connect_btn.clicked.connect(self._toggle_connection)
        card_layout.addWidget(self.connect_btn)

        self.status_label = QLabel("● 未连接")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("color: #ff5252; font-size: 13px; font-weight: 500;")
        card_layout.addWidget(self.status_label)

        card_wrapper = QHBoxLayout()
        card_wrapper.addStretch()
        card_wrapper.addWidget(card)
        card_wrapper.addStretch()
        vbox.addLayout(card_wrapper)

        vbox.addStretch(3)

    def _toggle_connection(self):
        if self.state.connected:
            self.tcp_worker.disconnect()
        else:
            host = self.ip_input.text().strip()
            port_text = self.port_input.text().strip()
            if not host or not port_text:
                self.status_label.setText("请输入 IP 和端口")
                self.status_label.setStyleSheet("color: #ffab40; font-size: 13px; font-weight: 500;")
                return
            try:
                port = int(port_text)
            except ValueError:
                self.status_label.setText("端口必须是数字")
                self.status_label.setStyleSheet("color: #ffab40; font-size: 13px; font-weight: 500;")
                return

            self._set_connecting(True)
            self.tcp_worker.connect_to(host, port)

    def _set_connecting(self, connecting):
        self._connecting = connecting
        self.connect_btn.setText("连接中..." if connecting else "连接板卡")
        self.connect_btn.setEnabled(not connecting)
        self.ip_input.setEnabled(not connecting)
        self.port_input.setEnabled(not connecting)
        if connecting:
            self.status_label.setText("正在连接...")
            self.status_label.setStyleSheet("color: #ffab40; font-size: 13px; font-weight: 500;")
            self._timeout_timer.start(8000)
        else:
            self._timeout_timer.stop()

    def _on_connect_timeout(self):
        if self._connecting:
            self._set_connecting(False)
            self.connect_btn.setEnabled(True)
            self.ip_input.setEnabled(True)
            self.port_input.setEnabled(True)
            self.connect_btn.setText("连接板卡")
            self.status_label.setText("连接超时")
            self.status_label.setStyleSheet("color: #ff5252; font-size: 13px; font-weight: 500;")

    def _on_connection_changed(self, connected, addr):
        if connected:
            self._set_connecting(False)
            self.connect_btn.setEnabled(True)
            self.connect_btn.setText("断开连接")
            self.status_label.setText("● 已连接")
            self.status_label.setStyleSheet("color: #69f0ae; font-size: 13px; font-weight: 500;")
            if self.ip_input.text().strip() not in _IP_HISTORY:
                _IP_HISTORY.insert(0, self.ip_input.text().strip())
                if len(_IP_HISTORY) > 5: _IP_HISTORY.pop()
            if self.port_input.text().strip() not in _PORT_HISTORY:
                _PORT_HISTORY.insert(0, self.port_input.text().strip())
        # Ignore disconnected signal while connecting — error handler deals with failure

    def _on_error(self, msg):
        self._set_connecting(False)
        self.connect_btn.setEnabled(True)
        self.ip_input.setEnabled(True)
        self.port_input.setEnabled(True)
        short = msg.split('] ')[-1] if '] ' in msg else msg
        self.status_label.setText(f"连接失败: {short}")
        self.status_label.setStyleSheet("color: #ff5252; font-size: 13px; font-weight: 500;")
