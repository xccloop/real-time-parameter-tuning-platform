from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QScrollArea, QFrame,
    QSplitter, QGridLayout
)
from PyQt5.QtCore import Qt

from app.backend.tcp_client import TcpWorker
from app.backend.parser import AppState
from app.ui.widgets.param_slider import ParamSlider
from app.ui.widgets.realtime_plot import RealtimePlot
from app.ui.widgets.log_console import LogConsole


class DashboardPage(QWidget):
    def __init__(self, tcp_worker: TcpWorker, state: AppState):
        super().__init__()
        self.tcp_worker = tcp_worker
        self.state = state
        self._sliders: dict = {}

        self._setup_ui()

        self.tcp_worker.param_updated.connect(self._on_param_updated)
        self.tcp_worker.log_received.connect(self._on_log_received)
        self.tcp_worker.connection_changed.connect(self._on_connection_changed)

    def _setup_ui(self):
        main_splitter = QSplitter(Qt.Horizontal)
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.addWidget(main_splitter)

        # ── Left: parameter list ──
        left_widget = QWidget()
        left_widget.setObjectName("dashboardLeft")
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(4, 4, 4, 4)

        left_title = QLabel("参数列表")
        left_title.setObjectName("sectionTitle")
        left_layout.addWidget(left_title)

        self.param_count = QLabel("等待数据...")
        self.param_count.setObjectName("paramCount")
        left_layout.addWidget(self.param_count)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setObjectName("paramScroll")
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.param_container = QWidget()
        self.param_layout = QVBoxLayout(self.param_container)
        self.param_layout.setSpacing(8)
        self.param_layout.addStretch()
        self.scroll_area.setWidget(self.param_container)
        left_layout.addWidget(self.scroll_area)

        main_splitter.addWidget(left_widget)

        # ── Right: plot + log ──
        right_splitter = QSplitter(Qt.Vertical)

        # Top-right: realtime plot
        plot_frame = QFrame()
        plot_frame.setObjectName("plotFrame")
        plot_layout = QVBoxLayout(plot_frame)
        plot_layout.setContentsMargins(4, 4, 4, 4)
        self.plot = RealtimePlot()
        plot_layout.addWidget(self.plot)
        right_splitter.addWidget(plot_frame)

        # Bottom-right: log console
        log_frame = QFrame()
        log_frame.setObjectName("logFrame")
        log_layout = QVBoxLayout(log_frame)
        log_layout.setContentsMargins(4, 4, 4, 4)
        log_title = QLabel("通信日志")
        log_title.setObjectName("sectionTitle")
        log_layout.addWidget(log_title)
        self.log_console = LogConsole()
        log_layout.addWidget(self.log_console)
        right_splitter.addWidget(log_frame)

        right_splitter.setSizes([350, 250])
        main_splitter.addWidget(right_splitter)
        main_splitter.setSizes([400, 900])

        # ── Bottom: command input ──
        bottom_row = QHBoxLayout()
        bottom_row.setContentsMargins(4, 0, 4, 4)

        self.cmd_input = QLineEdit()
        self.cmd_input.setPlaceholderText("输入命令，如 set speed 500，回车发送...")
        self.cmd_input.setObjectName("cmdInput")
        self.cmd_input.setFixedHeight(36)
        self.cmd_input.returnPressed.connect(self._send_command)
        bottom_row.addWidget(self.cmd_input)

        send_btn = QPushButton("发送")
        send_btn.setObjectName("sendBtn")
        send_btn.setFixedSize(70, 36)
        send_btn.setCursor(Qt.PointingHandCursor)
        send_btn.clicked.connect(self._send_command)
        bottom_row.addWidget(send_btn)

        # Wrap main_splitter + bottom in a vertical layout
        wrapper = QWidget()
        w_layout = QVBoxLayout(wrapper)
        w_layout.setContentsMargins(0, 0, 0, 0)
        w_layout.addWidget(main_splitter)
        w_layout.addLayout(bottom_row)

        main_layout.addWidget(wrapper)

    def _on_param_updated(self, name, param):
        if name in self._sliders:
            self._sliders[name].update_from_param(param)
        else:
            slider = ParamSlider(param)
            slider.value_changed.connect(self._on_slider_value_changed)
            self._sliders[name] = slider
            self.param_layout.insertWidget(self.param_layout.count() - 1, slider)

        self.plot.add_data_point(name, param.value)
        self.param_count.setText(f"参数: {len(self._sliders)} 个")

    def _on_log_received(self, ts, text):
        self.log_console.append_log(ts, text)

    def _on_slider_value_changed(self, name, value):
        self.tcp_worker.send(f"set {name} {value}")

    def _send_command(self):
        cmd = self.cmd_input.text().strip()
        if cmd:
            self.tcp_worker.send(cmd)
            self.cmd_input.clear()

    def _on_connection_changed(self, connected, addr):
        if not connected:
            for slider in self._sliders.values():
                slider.setEnabled(False)
        else:
            for slider in self._sliders.values():
                slider.setEnabled(True)
