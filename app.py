# -*- coding: utf-8 -*-
"""照片筛选工具 GUI 入口。"""
from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from core.i18n import tr
from gui.main_window import MainWindow
from gui.styles import apply_app_style


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(tr("app.name"))
    app.setOrganizationName("PhotoTriage")
    apply_app_style(app)

    win = MainWindow()
    win.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
