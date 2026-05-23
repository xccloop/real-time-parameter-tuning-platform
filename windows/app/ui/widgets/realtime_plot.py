import time
from collections import deque
from typing import Dict, Optional

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QComboBox
from PyQt5.QtCore import Qt


try:
    import pyqtgraph as pg
    HAS_PYQTGRAPH = True
except ImportError:
    HAS_PYQTGRAPH = False


MAX_POINTS = 200


class RealtimePlot(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("plotWidget")

        self._curves: Dict[str, object] = {}
        self._data: Dict[str, deque] = {}
        self._start_time = time.time()
        self._selected_param: Optional[str] = None
        self._all_params: Dict[str, object] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        if HAS_PYQTGRAPH:
            pg.setConfigOptions(antialias=True)
            self.plot_widget = pg.PlotWidget()
            self.plot_widget.setLabel('left', 'Value')
            self.plot_widget.setLabel('bottom', 'Time', units='s')
            self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
            self.plot_widget.setBackground('#1a1a2e')
            self._pen_colors = ['#00d2ff', '#ff6b6b', '#2ed573', '#ffa502',
                              '#a29bfe', '#fd79a8', '#00b894', '#fdcb6e']
            layout.addWidget(self.plot_widget)

        self.param_selector = QComboBox()
        self.param_selector.setObjectName("paramSelector")
        self.param_selector.setFixedHeight(28)
        self.param_selector.currentTextChanged.connect(self._on_selection_changed)
        layout.addWidget(self.param_selector)

    def add_data_point(self, name: str, value: float):
        self._all_params[name] = value

        if name not in self._data:
            self._data[name] = deque(maxlen=MAX_POINTS)
            if HAS_PYQTGRAPH:
                color = self._pen_colors[len(self._curves) % len(self._pen_colors)]
                self._curves[name] = self.plot_widget.plot(
                    [], [], pen=pg.mkPen(color=color, width=2), name=name
                )
            if self.param_selector.findText(name) == -1:
                self.param_selector.addItem(name)

        self._data[name].append((time.time() - self._start_time, value))

        if self._selected_param is None:
            self._selected_param = name
            self.param_selector.setCurrentText(name)

        if name == self._selected_param and HAS_PYQTGRAPH:
            self._update_curve(name)

    def _on_selection_changed(self, text):
        if text and text in self._data and HAS_PYQTGRAPH:
            self._selected_param = text
            self._update_curve(text)

    def _update_curve(self, name):
        if name in self._data:
            t, v = zip(*self._data[name]) if self._data[name] else ([], [])
            self._curves[name].setData(t, v)
