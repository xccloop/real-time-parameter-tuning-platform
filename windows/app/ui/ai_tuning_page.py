import time
from typing import Optional

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QSpinBox, QDoubleSpinBox,
    QCheckBox, QProgressBar, QTableWidget, QTableWidgetItem,
    QFrame, QGroupBox, QHeaderView
)
from PyQt5.QtCore import Qt, QTimer

from app.backend.tcp_client import TcpWorker
from app.backend.parser import AppState
from app.ai.pid_autotune import AITuner, TuningState


class AITuningPage(QWidget):
    def __init__(self, tcp_worker: TcpWorker, state: AppState):
        super().__init__()
        self.tcp_worker = tcp_worker
        self.state = state
        self._tuner: Optional[AITuner] = None
        self._running = False

        self._setup_ui()

        self.tcp_worker.param_updated.connect(self._on_param_updated)
        self.tcp_worker.connection_changed.connect(self._on_connection_changed)

        self._status_timer = QTimer()
        self._status_timer.timeout.connect(self._refresh_status)
        self._status_timer.start(500)

    def _setup_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)

        # ── LEFT: config ──
        left = QVBoxLayout()
        left.setSpacing(12)

        # Target config
        target_group = QGroupBox("调参目标")
        target_group.setObjectName("tuningGroup")
        tg_layout = QVBoxLayout(target_group)
        tg_layout.setSpacing(10)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("目标参数:"))
        self.target_param_combo = QComboBox()
        self.target_param_combo.setObjectName("targetCombo")
        self.target_param_combo.setMinimumWidth(120)
        row1.addWidget(self.target_param_combo)
        row1.addStretch()
        tg_layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("目标值:"))
        self.target_value_spin = QDoubleSpinBox()
        self.target_value_spin.setObjectName("targetSpin")
        self.target_value_spin.setRange(-99999, 99999)
        self.target_value_spin.setDecimals(1)
        self.target_value_spin.setValue(500)
        row2.addWidget(self.target_value_spin)
        row2.addStretch()
        tg_layout.addLayout(row2)

        row3 = QHBoxLayout()
        row3.addWidget(QLabel("允许超调:"))
        self.overshoot_spin = QDoubleSpinBox()
        self.overshoot_spin.setRange(0, 100)
        self.overshoot_spin.setValue(10)
        self.overshoot_spin.setSuffix("%")
        row3.addWidget(self.overshoot_spin)
        row3.addStretch()
        tg_layout.addLayout(row3)

        tg_layout.addWidget(QLabel("调节参数:"))
        self.kp_check = QCheckBox("kp")
        self.kp_check.setChecked(True)
        self.ki_check = QCheckBox("ki")
        self.ki_check.setChecked(True)
        self.kd_check = QCheckBox("kd")
        self.kd_check.setChecked(True)
        checkbox_row = QHBoxLayout()
        checkbox_row.addWidget(self.kp_check)
        checkbox_row.addWidget(self.ki_check)
        checkbox_row.addWidget(self.kd_check)
        checkbox_row.addStretch()
        tg_layout.addLayout(checkbox_row)

        left.addWidget(target_group)

        # Buttons
        btn_row = QHBoxLayout()
        self.start_btn = QPushButton("▶ 开始自动调参")
        self.start_btn.setObjectName("startTuneBtn")
        self.start_btn.setFixedHeight(40)
        self.start_btn.setCursor(Qt.PointingHandCursor)
        self.start_btn.clicked.connect(self._toggle_tuning)
        btn_row.addWidget(self.start_btn)

        self.stop_btn = QPushButton("■ 停止")
        self.stop_btn.setObjectName("stopTuneBtn")
        self.stop_btn.setFixedHeight(40)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setCursor(Qt.PointingHandCursor)
        self.stop_btn.clicked.connect(self._stop_tuning)
        btn_row.addWidget(self.stop_btn)
        left.addLayout(btn_row)

        # Current status
        status_group = QGroupBox("当前状态")
        status_group.setObjectName("tuningGroup")
        sg_layout = QVBoxLayout(status_group)
        self.current_value_lbl = QLabel("--")
        self.current_value_lbl.setObjectName("bigValue")
        sg_layout.addWidget(self.current_value_lbl)
        self.error_lbl = QLabel("目标: --    误差: --")
        sg_layout.addWidget(self.error_lbl)
        self.trend_lbl = QLabel("趋势: --")
        sg_layout.addWidget(self.trend_lbl)
        left.addWidget(status_group)

        left.addStretch()
        root.addLayout(left, 1)

        # ── RIGHT: analysis + history ──
        right = QVBoxLayout()
        right.setSpacing(12)

        # AI analysis box
        analysis_group = QGroupBox("AI 分析")
        analysis_group.setObjectName("tuningGroup")
        ag_layout = QVBoxLayout(analysis_group)

        strategy_row = QHBoxLayout()
        strategy_row.addWidget(QLabel("当前策略:"))
        self.strategy_lbl = QLabel("等待启动")
        self.strategy_lbl.setObjectName("strategyLabel")
        strategy_row.addWidget(self.strategy_lbl)
        strategy_row.addStretch()
        ag_layout.addLayout(strategy_row)

        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("tuneProgress")
        self.progress_bar.setFixedHeight(6)
        ag_layout.addWidget(self.progress_bar)

        self.status_text = QLabel("")
        self.status_text.setWordWrap(True)
        ag_layout.addWidget(self.status_text)

        self.eta_lbl = QLabel("")
        ag_layout.addWidget(self.eta_lbl)

        right.addWidget(analysis_group)

        # Tuning history
        hist_group = QGroupBox("调参历史")
        hist_group.setObjectName("tuningGroup")
        hg_layout = QVBoxLayout(hist_group)

        self.history_table = QTableWidget(0, 4)
        self.history_table.setObjectName("historyTable")
        self.history_table.setHorizontalHeaderLabels(["#", "参数", "效果", ""])
        self.history_table.horizontalHeader().setStretchLastSection(True)
        self.history_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.history_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.history_table.setSelectionBehavior(QTableWidget.SelectRows)
        hg_layout.addWidget(self.history_table)

        right.addWidget(hist_group)

        root.addLayout(right, 2)

    def _toggle_tuning(self):
        if self._running:
            self._stop_tuning()
            return

        target_param = self.target_param_combo.currentText()
        if not target_param:
            return

        target_val = self.target_value_spin.value()
        overshoot = self.overshoot_spin.value() / 100.0

        tunable = []
        if self.kp_check.isChecked(): tunable.append("kp")
        if self.ki_check.isChecked(): tunable.append("ki")
        if self.kd_check.isChecked(): tunable.append("kd")

        if not tunable:
            return

        self._tuner = AITuner(
            tcp_worker=self.tcp_worker,
            state=self.state,
            target_param=target_param,
            target_value=target_val,
            overshoot_ratio=overshoot,
            tunable_params=tunable
        )
        self._tuner.state_changed.connect(self._on_tuner_state)
        self._tuner.history_added.connect(self._on_history_added)
        self._tuner.finished.connect(self._on_tuning_finished)
        self._tuner.start()

        self._running = True
        self.start_btn.setText("⏸ 运行中...")
        self.stop_btn.setEnabled(True)

    def _stop_tuning(self):
        if self._tuner:
            self._tuner.stop()
        self._set_idle()

    def _set_idle(self):
        self._running = False
        self.start_btn.setText("▶ 开始自动调参")
        self.stop_btn.setEnabled(False)

    def _on_tuner_state(self, state: TuningState):
        self.strategy_lbl.setText(state.strategy)
        self.progress_bar.setValue(int(state.progress * 100))
        self.status_text.setText(f"误差: {state.error:.1f} ({state.error_pct:.1f}%)")
        self.trend_lbl.setText(f"趋势: {state.trend}")
        if state.eta_seconds > 0:
            self.eta_lbl.setText(f"预计还需: {state.eta_seconds:.0f} 秒")

    def _on_history_added(self, step, params, result):
        row = self.history_table.rowCount()
        self.history_table.insertRow(row)
        self.history_table.setItem(row, 0, QTableWidgetItem(str(step)))
        self.history_table.setItem(row, 1, QTableWidgetItem(params))
        self.history_table.setItem(row, 2, QTableWidgetItem(result))
        icon = "✓" if "✓" in result or "stable" in result.lower() else ""
        self.history_table.setItem(row, 3, QTableWidgetItem(icon))
        self.history_table.scrollToBottom()

    def _on_tuning_finished(self, success, message):
        self._set_idle()
        self.status_text.setText(message)
        self.strategy_lbl.setText("完成" if success else "未完成")

    def _on_param_updated(self, name, param):
        if self.target_param_combo.findText(name) == -1:
            self.target_param_combo.addItem(name)

        target = self.target_param_combo.currentText()
        if name == target:
            target_val = self.target_value_spin.value()
            error = target_val - param.value
            self.current_value_lbl.setText(f"{param.value}")
            self.error_lbl.setText(f"目标: {target_val}    误差: {error:.1f}")

    def _refresh_status(self):
        target = self.target_param_combo.currentText()
        if target and target in self.state.parameters:
            p = self.state.parameters[target]
            target_val = self.target_value_spin.value()
            error = target_val - p.value
            self.current_value_lbl.setText(f"{p.value}")
            self.error_lbl.setText(f"目标: {target_val}    误差: {error:.1f}")

    def _on_connection_changed(self, connected, addr):
        if not connected and self._running:
            self._stop_tuning()
