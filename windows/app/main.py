import sys
import os

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt

from app.ui.main_window import MainWindow


def main():
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName("可交互调车系统")
    app.setOrganizationName("EpollTuning")

    if getattr(sys, 'frozen', False):
        base = sys._MEIPASS
        qss_path = os.path.join(base, 'app', 'ui', 'styles', 'theme.qss')
    else:
        qss_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'ui', 'styles', 'theme.qss')
        if not os.path.exists(qss_path):
            qss_path = os.path.join(os.path.dirname(__file__), 'ui', 'styles', 'theme.qss')
    if os.path.exists(qss_path):
        with open(qss_path, 'r', encoding='utf-8') as f:
            app.setStyleSheet(f.read())

    window = MainWindow()
    window.show()

    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
