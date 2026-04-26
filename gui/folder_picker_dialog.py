# -*- coding: utf-8 -*-
"""带照片预览的文件夹选择器。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QDir, QSize, Qt, QTimer
from PySide6.QtGui import QIcon, QImageReader, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QFileSystemModel,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from core.i18n import tr

from triage import scan_folder

from .styles import mark_primary


class FolderPickerDialog(QDialog):
    """左侧目录树,右侧显示当前目录里的照片缩略图。"""

    def __init__(self, start: Path | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("folder_picker.title"))
        self.resize(1100, 720)
        self.selected_folder: Path | None = None
        self._preview_pairs: list[tuple[Path, Path | None]] = []
        self._preview_index = 0
        self._build_ui()
        self._wire()
        self._go_to(start if start and start.is_dir() else Path.home())

    def _build_ui(self):
        self.model = QFileSystemModel(self)
        self.model.setFilter(QDir.AllDirs | QDir.NoDotAndDotDot | QDir.Drives)
        self.model.setRootPath(QDir.rootPath())

        self.tree = QTreeView()
        self.tree.setModel(self.model)
        self.tree.setHeaderHidden(True)
        self.tree.setAnimated(True)
        self.tree.setIndentation(16)
        self.tree.setUniformRowHeights(True)
        self.tree.setSelectionMode(QAbstractItemView.SingleSelection)
        for col in range(1, self.model.columnCount()):
            self.tree.hideColumn(col)

        self.path_edit = QLineEdit()
        self.path_edit.setReadOnly(True)
        self.path_edit.setPlaceholderText(tr("folder_picker.path_placeholder"))

        self.stats_label = QLabel(tr("folder_picker.none"))
        self.stats_label.setProperty("muted", True)

        self.preview = QListWidget()
        self.preview.setViewMode(QListWidget.IconMode)
        self.preview.setMovement(QListWidget.Static)
        self.preview.setResizeMode(QListWidget.Adjust)
        self.preview.setSelectionMode(QAbstractItemView.NoSelection)
        self.preview.setIconSize(QSize(150, 150))
        self.preview.setGridSize(QSize(176, 204))
        self.preview.setSpacing(8)
        self.preview.setWordWrap(False)

        self.empty_label = QLabel(tr("folder_picker.empty"))
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setProperty("emptyState", True)

        right = QWidget()
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(14, 12, 14, 12)
        right_lay.setSpacing(10)
        right_lay.addWidget(QLabel(tr("folder_picker.current")))
        right_lay.addWidget(self.path_edit)
        right_lay.addWidget(self.stats_label)
        right_lay.addWidget(self.preview, 1)

        split = QSplitter(Qt.Horizontal)
        split.addWidget(self.tree)
        split.addWidget(right)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setSizes([320, 760])

        self.use_btn = QPushButton(tr("folder_picker.use"))
        mark_primary(self.use_btn)
        self.open_btn = QPushButton(tr("folder_picker.open_explorer"))
        self.buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        self.buttons.addButton(self.open_btn, QDialogButtonBox.ActionRole)
        self.buttons.addButton(self.use_btn, QDialogButtonBox.AcceptRole)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.addWidget(split, 1)
        lay.addWidget(self.buttons)

        self._preview_timer = QTimer(self)
        self._preview_timer.setInterval(0)
        self._preview_timer.timeout.connect(self._add_next_preview)

    def _wire(self):
        self.tree.selectionModel().currentChanged.connect(self._on_tree_current)
        self.tree.doubleClicked.connect(lambda _idx: self._accept_if_ready())
        self.use_btn.clicked.connect(self._accept_if_ready)
        self.open_btn.clicked.connect(self._open_selected_folder)
        self.buttons.rejected.connect(self.reject)

    def _go_to(self, folder: Path):
        idx = self.model.index(str(folder))
        if idx.isValid():
            self.tree.setCurrentIndex(idx)
            self.tree.scrollTo(idx)
            self._set_folder(folder)

    def _on_tree_current(self, index, _previous):
        path = Path(self.model.filePath(index))
        if path.is_dir():
            self._set_folder(path)

    def _set_folder(self, folder: Path):
        self.selected_folder = folder
        self.path_edit.setText(str(folder))
        self.preview.clear()
        self._preview_timer.stop()
        try:
            pairs = scan_folder(folder)
        except Exception as e:  # noqa: BLE001
            self._preview_pairs = []
            self.stats_label.setText(tr("folder_picker.scan_failed", error=e))
            self.use_btn.setEnabled(False)
            return
        raw_count = sum(1 for _, raw in pairs if raw)
        self.stats_label.setText(tr("folder_picker.stats", total=len(pairs), raw=raw_count))
        self.use_btn.setEnabled(folder.is_dir())
        self._preview_pairs = pairs[:120]
        self._preview_index = 0
        if not self._preview_pairs:
            item = QListWidgetItem(tr("folder_picker.empty"))
            item.setTextAlignment(Qt.AlignCenter)
            self.preview.addItem(item)
        else:
            self._preview_timer.start()

    def _add_next_preview(self):
        if self._preview_index >= len(self._preview_pairs):
            self._preview_timer.stop()
            return
        jpg, raw = self._preview_pairs[self._preview_index]
        self._preview_index += 1
        reader = QImageReader(str(jpg))
        reader.setAutoTransform(True)
        original = reader.size()
        if original.isValid():
            original.scale(QSize(150, 150), Qt.KeepAspectRatio)
            reader.setScaledSize(original)
        image = reader.read()
        if image.isNull():
            icon = QIcon()
        else:
            icon = QIcon(QPixmap.fromImage(image))
        suffix = " + RAW" if raw else ""
        item = QListWidgetItem(icon, f"{jpg.name}{suffix}")
        item.setToolTip(str(jpg))
        self.preview.addItem(item)

    def _accept_if_ready(self):
        if self.selected_folder and self.selected_folder.is_dir():
            self.accept()

    def _open_selected_folder(self):
        if not self.selected_folder:
            return
        from .preview_window import open_in_system
        open_in_system(self.selected_folder)
