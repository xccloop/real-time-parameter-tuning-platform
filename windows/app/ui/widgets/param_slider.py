from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel,
    QSlider, QPushButton, QFrame
)
from PyQt5.QtCore import Qt, pyqtSignal

from app.backend.parser import Parameter


_STEP_SIZES = {10, 5, 1, 0.1, 0.01}


def _best_step(rng: float) -> float:
    for s in sorted(_STEP_SIZES):
        if rng / s <= 200:
            return s
    return 1.0


class ParamSlider(QFrame):
    value_changed = pyqtSignal(str, float)

    def __init__(self, param: Parameter):
        super().__init__()
        self.setObjectName("paramCard")
        self.param_name = param.name
        self._range = param.max_val - param.min_val
        self._step = _best_step(self._range)
        self._updating = False

        self._setup_ui(param)

    def _setup_ui(self, param: Parameter):
        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(14, 10, 14, 10)
        vbox.setSpacing(6)

        # Header: name + value
        header = QHBoxLayout()
        name_lbl = QLabel(param.name)
        name_lbl.setObjectName("paramName")
        header.addWidget(name_lbl)
        header.addStretch()

        self.value_lbl = QLabel(str(param.value))
        self.value_lbl.setObjectName("paramValue")
        header.addWidget(self.value_lbl)
        vbox.addLayout(header)

        # Slider row
        slider_row = QHBoxLayout()
        slider_row.setSpacing(8)

        self.min_lbl = QLabel(str(param.min_val))
        self.min_lbl.setObjectName("rangeLabel")
        slider_row.addWidget(self.min_lbl)

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setMinimum(0)
        self.slider.setMaximum(max(1, int(self._range / self._step)))
        self.slider.setValue(int((param.value - param.min_val) / self._step))
        self.slider.setCursor(Qt.PointingHandCursor)
        self.slider.valueChanged.connect(self._on_slider_changed)
        self.slider.sliderReleased.connect(self._on_slider_released)
        slider_row.addWidget(self.slider)

        self.max_lbl = QLabel(str(param.max_val))
        self.max_lbl.setObjectName("rangeLabel")
        slider_row.addWidget(self.max_lbl)
        vbox.addLayout(slider_row)

        # Range text
        range_text = QLabel(f"[{param.min_val} - {param.max_val}]")
        range_text.setObjectName("rangeText")
        vbox.addWidget(range_text)

        # Quick adjust buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)

        for delta in [-10, -1, +1, +10]:
            label = f"{delta:+d}" if delta > 0 else str(delta)
            btn = QPushButton(label)
            btn.setObjectName("adjustBtn")
            btn.setFixedSize(40, 26)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda checked, d=delta: self._quick_adjust(d))
            btn_row.addWidget(btn)

        btn_row.addStretch()
        vbox.addLayout(btn_row)

        # Description
        desc_lbl = QLabel(param.description)
        desc_lbl.setObjectName("paramDesc")
        vbox.addWidget(desc_lbl)

    def update_from_param(self, param: Parameter):
        self._updating = True
        val = int((param.value - param.min_val) / self._step)
        self.slider.setValue(max(0, min(self.slider.maximum(), val)))
        self.value_lbl.setText(str(param.value))
        self._updating = False

    def _on_slider_changed(self, slider_val):
        if self._updating:
            return
        val = self.min_val() + slider_val * self._step
        val = round(val, 3)
        self.value_lbl.setText(str(val))

    def _on_slider_released(self):
        slider_val = self.slider.value()
        val = self.min_val() + slider_val * self._step
        val = round(val, 3)
        self.value_changed.emit(self.param_name, val)

    def _quick_adjust(self, delta):
        current_val = self.min_val() + self.slider.value() * self._step
        new_val = round(current_val + delta, 3)
        new_val = max(self.min_val(), min(self.max_val(), new_val))
        slider_val = int((new_val - self.min_val()) / self._step)
        self.slider.setValue(slider_val)
        self.value_changed.emit(self.param_name, new_val)

    def min_val(self) -> float:
        return float(self.min_lbl.text())

    def max_val(self) -> float:
        return float(self.max_lbl.text())
