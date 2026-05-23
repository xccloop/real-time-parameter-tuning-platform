from PyQt5.QtWidgets import (
    QMainWindow, QStackedWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QWidget, QFrame
)
from PyQt5.QtCore import Qt, QSize

from app.backend.parser import AppState
from app.backend.tcp_client import TcpWorker
from app.ui.connect_page import ConnectPage
from app.ui.dashboard_page import DashboardPage
from app.ui.ai_tuning_page import AITuningPage


class NavButton(QPushButton):
    def __init__(self, text, icon_char=""):
        super().__init__(f"  {icon_char}  {text}" if icon_char else text)
        self.setCheckable(True)
        self.setFixedHeight(44)
        self.setCursor(Qt.PointingHandCursor)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("可交互调车系统")
        self.setMinimumSize(1280, 800)
        self.resize(1400, 880)

        self.state = AppState()
        self.tcp_worker = TcpWorker(self.state)

        self._setup_ui()

        self.tcp_worker.connection_changed.connect(self._on_connection_changed)
        self.tcp_worker.error_occurred.connect(self._on_error)

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Navigation bar
        nav = QFrame()
        nav.setObjectName("navbar")
        nav.setFixedHeight(56)
        nav_layout = QHBoxLayout(nav)
        nav_layout.setContentsMargins(16, 4, 16, 4)

        title = QLabel("可交互调车系统")
        title.setObjectName("navTitle")
        nav_layout.addWidget(title)
        nav_layout.addStretch()

        self.btn_connect = NavButton("连接", "")
        self.btn_dashboard = NavButton("仪表盘", "")
        self.btn_ai = NavButton("AI 调参", "")
        self.btn_dashboard.setEnabled(False)
        self.btn_ai.setEnabled(False)

        self.btn_connect.clicked.connect(lambda: self._switch_page(0))
        self.btn_dashboard.clicked.connect(lambda: self._switch_page(1))
        self.btn_ai.clicked.connect(lambda: self._switch_page(2))

        nav_layout.addWidget(self.btn_connect)
        nav_layout.addWidget(self.btn_dashboard)
        nav_layout.addWidget(self.btn_ai)

        self._nav_buttons = [self.btn_connect, self.btn_dashboard, self.btn_ai]

        # Status indicator
        self.status_indicator = QLabel("● 未连接")
        self.status_indicator.setObjectName("statusIndicator")
        self.status_indicator.setStyleSheet("color: #ff4757;")
        nav_layout.addWidget(self.status_indicator)

        root.addWidget(nav)

        # Line separator
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setObjectName("navSep")
        root.addWidget(sep)

        # Stacked pages
        self.stack = QStackedWidget()
        self.connect_page = ConnectPage(self.tcp_worker, self.state)
        self.dashboard_page = DashboardPage(self.tcp_worker, self.state)
        self.ai_page = AITuningPage(self.tcp_worker, self.state)

        self.stack.addWidget(self.connect_page)
        self.stack.addWidget(self.dashboard_page)
        self.stack.addWidget(self.ai_page)

        root.addWidget(self.stack)

        self._switch_page(0)

    def _switch_page(self, index):
        self.stack.setCurrentIndex(index)
        for i, btn in enumerate(self._nav_buttons):
            btn.setChecked(i == index)

    def _on_connection_changed(self, connected, addr):
        if connected:
            self.status_indicator.setText(f"● 已连接 {addr}")
            self.status_indicator.setStyleSheet("color: #2ed573;")
            self.btn_dashboard.setEnabled(True)
            self.btn_ai.setEnabled(True)
            self._switch_page(1)
        else:
            self.status_indicator.setText("● 未连接")
            self.status_indicator.setStyleSheet("color: #ff4757;")
            self.btn_dashboard.setEnabled(False)
            self.btn_ai.setEnabled(False)
            self._switch_page(0)

    def _on_error(self, msg):
        pass

    def closeEvent(self, event):
        self.tcp_worker.disconnect()
        super().closeEvent(event)
