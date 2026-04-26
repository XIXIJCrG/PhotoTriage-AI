# -*- coding: utf-8 -*-
"""文件夹导航侧栏:当前目录 + 最近目录 + 资源管理器跳转。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.i18n import tr

from .preview_window import open_in_system
from .utils import app_settings


HISTORY_KEY = "history/folders"
HISTORY_LIMIT = 50


class HistorySidebar(QWidget):
    """更像资源管理器的轻量目录跳转区。"""

    folder_selected = Signal(Path)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_folder: Path | None = None
        self._build_ui()
        self._load()

    def _build_ui(self):
        self.setMaximumWidth(280)
        self.setMinimumWidth(220)
        self.setProperty("panel", "sidebar")

        title = QLabel(tr("sidebar.title"))
        title.setProperty("sectionTitle", True)

        self.current_label = QLabel(tr("sidebar.no_folder"))
        self.current_label.setWordWrap(True)
        self.current_label.setProperty("pathLabel", True)

        self.open_current_btn = QPushButton(tr("sidebar.open_current"))
        self.open_current_btn.clicked.connect(self._open_current)
        self.open_current_btn.setEnabled(False)

        recent = QLabel(tr("sidebar.recent"))
        recent.setProperty("subTitle", True)

        self.list = QListWidget()
        self.list.setObjectName("FolderHistoryList")
        self.list.itemActivated.connect(self._on_item_activated)
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._on_context_menu)

        clear_btn = QPushButton(tr("sidebar.clear"))
        clear_btn.clicked.connect(self._clear_history)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)
        lay.addWidget(title)
        lay.addWidget(self.current_label)
        lay.addWidget(self.open_current_btn)
        lay.addSpacing(8)
        lay.addWidget(recent)
        lay.addWidget(self.list, 1)
        lay.addWidget(clear_btn)

    def _load(self):
        raw = app_settings().value(HISTORY_KEY, [])
        if isinstance(raw, str):
            raw = [raw]
        elif not isinstance(raw, (list, tuple)):
            raw = []
        self.list.clear()
        for path_str in raw or []:
            p = Path(path_str)
            item = QListWidgetItem(p.name or path_str)
            item.setToolTip(path_str)
            item.setData(Qt.UserRole, path_str)
            if not p.is_dir():
                item.setForeground(Qt.gray)
            self.list.addItem(item)

    def push_folder(self, folder: Path):
        folder = Path(folder)
        self.current_folder = folder
        self.current_label.setText(str(folder))
        self.open_current_btn.setEnabled(folder.is_dir())

        folder_str = str(folder.resolve())
        raw = app_settings().value(HISTORY_KEY, []) or []
        if isinstance(raw, str):
            raw = [raw]
        elif not isinstance(raw, (list, tuple)):
            raw = []
        raw = [x for x in raw if isinstance(x, str) and x != folder_str]
        raw.insert(0, folder_str)
        app_settings().setValue(HISTORY_KEY, raw[:HISTORY_LIMIT])
        self._load()

    def _clear_history(self):
        app_settings().setValue(HISTORY_KEY, [])
        self.list.clear()

    def _open_current(self):
        if self.current_folder and self.current_folder.is_dir():
            open_in_system(self.current_folder)

    def _on_item_activated(self, item: QListWidgetItem):
        path_str = item.data(Qt.UserRole)
        if not path_str:
            return
        p = Path(path_str)
        if p.is_dir():
            self.folder_selected.emit(p)

    def _on_context_menu(self, pos):
        item = self.list.itemAt(pos)
        if item is None:
            return
        path_str = item.data(Qt.UserRole)
        if not path_str:
            return
        p = Path(path_str)
        menu = QMenu(self)
        act_select = QAction(tr("sidebar.switch"), self)
        act_select.triggered.connect(lambda: self._on_item_activated(item))
        act_open = QAction(tr("sidebar.open_explorer"), self)
        act_open.triggered.connect(lambda: open_in_system(p) if p.is_dir() else None)
        act_remove = QAction(tr("sidebar.remove"), self)
        act_remove.triggered.connect(lambda: self._remove_item(item))
        menu.addAction(act_select)
        menu.addAction(act_open)
        menu.addSeparator()
        menu.addAction(act_remove)
        menu.exec(self.list.mapToGlobal(pos))

    def _remove_item(self, item: QListWidgetItem):
        path_str = item.data(Qt.UserRole)
        if not path_str:
            return
        raw = app_settings().value(HISTORY_KEY, []) or []
        if isinstance(raw, str):
            raw = [raw]
        elif not isinstance(raw, (list, tuple)):
            raw = []
        raw = [x for x in raw if isinstance(x, str) and x != path_str]
        app_settings().setValue(HISTORY_KEY, raw)
        self._load()
