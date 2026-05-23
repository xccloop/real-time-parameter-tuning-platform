from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QFrame, QSpacerItem, QSizePolicy
)
from PyQt5.QtCore import Qt, QTimer

from app.backend.tcp_client import TcpWorker
from app.backend.parser import AppState


_IP_HISTORY = ["10.163.14.121"]
_PORT_HISTORY = ["9000"]


class ConnectPage(QWidget):
    def __init__(self, tcp_worker: TcpWorker, state: AppState):
        super().__init__()
        self.tcp_worker = tcp_worker
        self.state = state
        self._connecting = False

        self._setup_ui()

        self.tcp_worker.connection_changed.connect(self._on_connection_changed)
        self.tcp_worker.error_occurred.connect(self._on_error)

    def _setup_ui(self):
        vbox = QVBoxLayout(self)
        vbox.setAlignment(Qt.AlignCenter)

        vbox.addStretch(2)

        # Logo area
        logo = QLabel("可交互调车系统")
        logo.setObjectName("logo")
        logo.setAlignment(Qt.AlignCenter)
        vbox.addWidget(logo)

        subtitle = QLabel("Real-Time Parameter Tuning Platform")
        subtitle.setObjectName("subtitle")
        subtitle.setAlignment(Qt.AlignCenter)
        vbox.addWidget(subtitle)

        version = QLabel("v2.0")
        version.setObjectName("versionLabel")
        version.setAlignment(Qt.AlignCenter)
        vbox.addWidget(version)

        vbox.addSpacing(40)

        # Connection card
        card = QFrame()
        card.setObjectName("connectCard")
        card.setFixedWidth(420)
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(18)
        card_layout.setContentsMargins(30, 30, 30, 30)

        # IP input
        ip_label = QLabel("板卡 IP 地址")
        ip_label.setObjectName("fieldLabel")
        card_layout.addWidget(ip_label)

        self.ip_input = QLineEdit()
        self.ip_input.setPlaceholderText("输入板卡 IP 地址...")
        self.ip_input.setObjectName("ipInput")
        self.ip_input.setFixedHeight(44)
        if _IP_HISTORY:
            self.ip_input.setText(_IP_HISTORY[0])
        card_layout.addWidget(self.ip_input)

        # Port input
        port_label = QLabel("端口")
        port_label.setObjectName("fieldLabel")
        card_layout.addWidget(port_label)

        self.port_input = QLineEdit()
        self.port_input.setPlaceholderText("输入端口...")
        self.port_input.setObjectName("portInput")
        self.port_input.setFixedHeight(44)
        self.port_input.setFixedWidth(140)
        if _PORT_HISTORY:
            self.port_input.setText(_PORT_HISTORY[0])
        card_layout.addWidget(self.port_input)

        card_layout.addSpacing(12)

        # Connect button
        self.connect_btn = QPushButton("连接板卡")
        self.connect_btn.setObjectName("connectBtn")
        self.connect_btn.setFixedHeight(48)
        self.connect_btn.setCursor(Qt.PointingHandCursor)
        self.connect_btn.clicked.connect(self._toggle_connection)
        card_layout.addWidget(self.connect_btn)

        # Status
        self.status_label = QLabel("● 未连接")
        self.status_label.setObjectName("connectStatus")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("color: #ff4757;")
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
                self._set_status("请输入 IP 和端口", "#ffa502")
                return
            try:
                port = int(port_text)
            except ValueError:
                self._set_status("端口必须是数字", "#ffa502")
                return

            self._set_connecting(True)
            self.tcp_worker.connect_to(host, port)

    def _set_connecting(self, connecting):
        self._connecting = connecting
        self.connect_btn.setText("连接中..." if connecting else "连接板卡")
        self.connect_btn.setEnabled(not connecting)
        self.ip_input.setEnabled(not connecting)
        self.port_input.setEnabled(not connecting)

    def _on_connection_changed(self, connected, addr):
        self._set_connecting(False)
        self.connect_btn.setEnabled(True)
        if connected:
            self.connect_btn.setText("断开连接")
            self._set_status("● 已连接", "#2ed573")
            if self.ip_input.text().strip() not in _IP_HISTORY:
                _IP_HISTORY.insert(0, self.ip_input.text().strip())
                if len(_IP_HISTORY) > 5:
                    _IP_HISTORY.pop()
            if self.port_input.text().strip() not in _PORT_HISTORY:
                _PORT_HISTORY.insert(0, self.port_input.text().strip())
        else:
            self.connect_btn.setText("连接板卡")
            self._set_status("● 未连接", "#ff4757")
            self.ip_input.setEnabled(True)
            self.port_input.setEnabled(True)

    def _on_error(self, msg):
        self._set_connecting(False)
        self.connect_btn.setEnabled(True)
        self.ip_input.setEnabled(True)
        self.port_input.setEnabled(True)
        self._set_status(f"连接失败: {msg}", "#ff4757")

    def _set_status(self, text, color):
        self.status_label.setText(text)
        self.status_label.setStyleSheet(f"color: {color};")
