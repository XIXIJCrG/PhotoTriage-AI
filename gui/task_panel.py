# -*- coding: utf-8 -*-
"""任务面板:文件夹选择、并发数、开始按钮。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from core.i18n import tr

from triage import CONCURRENCY, scan_folder, load_processed

from .folder_picker_dialog import FolderPickerDialog
from .prompt_manager import DEFAULT_PROFILE_NAME, PromptStore
from .styles import mark_primary
from .utils import app_settings


class TaskPanel(QWidget):
    """任务配置面板。发出 start_requested / stop_requested 信号。"""

    start_requested = Signal(Path, int, bool, str)   # folder, concurrency, write_meta, prompt_profile_name
    stop_requested = Signal()
    folder_changed = Signal(Path)
    edit_prompts_requested = Signal()

    def __init__(self, prompt_store: PromptStore | None = None, parent=None):
        super().__init__(parent)
        self._building_ui = True
        self.folder: Path | None = None
        self._running = False
        self._server_ok = False
        self.prompt_store = prompt_store or PromptStore()
        self._build_ui()
        self._load_last_folder()
        self._building_ui = False
        self._refresh_start_btn()

    # ---------- UI ----------
    def _build_ui(self):
        self.setAcceptDrops(True)

        # 文件夹
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText(tr("task.folder_placeholder"))
        self.path_edit.setReadOnly(True)
        browse_btn = QPushButton(tr("action.browse"))
        browse_btn.clicked.connect(self._on_browse)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel(tr("task.photo_folder")))
        row1.addWidget(self.path_edit, 1)
        row1.addWidget(browse_btn)

        # 并发 + 元数据
        self.conc_spin = QSpinBox()
        self.conc_spin.setRange(1, 32)
        try:
            saved_conc = int(app_settings().value("task/concurrency", CONCURRENCY))
        except (TypeError, ValueError):
            saved_conc = CONCURRENCY
        self.conc_spin.setValue(max(1, min(32, saved_conc)))
        self.conc_spin.valueChanged.connect(
            lambda v: app_settings().setValue("task/concurrency", int(v)))

        self.meta_cb = QCheckBox(tr("task.write_xmp"))
        # 统一存 bool,避免 "true"/"false"/True/False 混用
        self.meta_cb.setChecked(
            bool(app_settings().value("task/write_meta", True, type=bool)))
        self.meta_cb.toggled.connect(
            lambda v: app_settings().setValue("task/write_meta", bool(v)))

        # Prompt profile 选择
        self.profile_combo = QComboBox()
        self.profile_combo.setMinimumWidth(140)
        self._refresh_profile_combo()

        self.edit_prompt_btn = QPushButton(tr("task.edit"))
        self.edit_prompt_btn.setFixedWidth(60)
        self.edit_prompt_btn.setToolTip(tr("task.edit_prompt_tooltip"))
        self.edit_prompt_btn.clicked.connect(self.edit_prompts_requested)

        self.info_label = QLabel("")
        self.info_label.setStyleSheet("color: #5A6270;")

        row2 = QHBoxLayout()
        row2.addWidget(QLabel(tr("task.concurrency")))
        row2.addWidget(self.conc_spin)
        row2.addSpacing(12)
        row2.addWidget(self.meta_cb)
        row2.addSpacing(12)
        row2.addWidget(QLabel("Prompt:"))
        row2.addWidget(self.profile_combo)
        row2.addWidget(self.edit_prompt_btn)
        row2.addSpacing(12)
        row2.addWidget(self.info_label, 1)

        # 操作按钮
        self.start_btn = QPushButton(tr("action.start_analysis"))
        self.start_btn.setFixedHeight(36)
        mark_primary(self.start_btn)
        self.start_btn.clicked.connect(self._on_start)

        self.stop_btn = QPushButton(tr("action.stop"))
        self.stop_btn.setFixedHeight(36)
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._on_stop)

        row3 = QHBoxLayout()
        row3.addStretch(1)
        row3.addWidget(self.stop_btn)
        row3.addWidget(self.start_btn)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(8)
        lay.addLayout(row1)
        lay.addLayout(row2)
        lay.addLayout(row3)

    def _load_last_folder(self):
        last = app_settings().value("task/last_folder", "")
        if last and Path(last).is_dir():
            self._set_folder(Path(last))

    # ---------- 文件夹 ----------
    def _on_browse(self):
        dlg = FolderPickerDialog(self.folder, self)
        if dlg.exec() and dlg.selected_folder:
            self._set_folder(dlg.selected_folder)

    def _set_folder(self, folder: Path):
        self.folder = folder
        self.path_edit.setText(str(folder))
        app_settings().setValue("task/last_folder", str(folder))
        self._scan_and_show()
        self.folder_changed.emit(folder)

    def _scan_and_show(self):
        """扫描目录,显示 JPG 总数 / 已处理 / 待处理。"""
        if not self.folder or not self.folder.is_dir():
            self.info_label.setText("")
            return
        try:
            pairs = scan_folder(self.folder)
            _, processed = load_processed(self.folder)
            todo = [p for p in pairs if p[0].name not in processed]
            raw_count = sum(1 for _, r in pairs if r)
            self.info_label.setText(tr(
                "task.scan_summary",
                total=len(pairs),
                raw=raw_count,
                processed=len(processed),
                todo=len(todo),
            ))
        except Exception as e:  # noqa: BLE001
            self.info_label.setText(tr("task.scan_failed", error=e))
        self._refresh_start_btn()

    # ---------- 拖拽 ----------
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        if not urls:
            return
        path = Path(urls[0].toLocalFile())
        if path.is_dir():
            self._set_folder(path)
        elif path.is_file():
            self._set_folder(path.parent)

    # ---------- 开始/停止 ----------
    def _on_start(self):
        if not self.folder or not self.folder.is_dir():
            return
        profile_name = self.profile_combo.currentData() or self.profile_combo.currentText() or DEFAULT_PROFILE_NAME
        self.start_requested.emit(
            self.folder, self.conc_spin.value(),
            self.meta_cb.isChecked(), profile_name)

    def _refresh_profile_combo(self):
        current = self.profile_combo.currentData() if self.profile_combo.count() else ""
        # 首次调用才连一次持久化
        if self.profile_combo.count() == 0:
            self.profile_combo.currentIndexChanged.connect(
                lambda _idx: app_settings().setValue(
                    "task/prompt_profile", self.profile_combo.currentData() or DEFAULT_PROFILE_NAME))
        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()
        names = self.prompt_store.list_names()
        for name in names:
            display = tr("prompt.default") if name == DEFAULT_PROFILE_NAME else name
            self.profile_combo.addItem(display, name)
        saved = app_settings().value("task/prompt_profile", DEFAULT_PROFILE_NAME)
        target = current if current in names else (saved if saved in names else DEFAULT_PROFILE_NAME)
        idx = self.profile_combo.findData(target)
        if idx >= 0:
            self.profile_combo.setCurrentIndex(idx)
        self.profile_combo.blockSignals(False)

    def reload_prompt_profiles(self):
        """Prompt 编辑器关闭后外部调用一次,刷新下拉。"""
        self._refresh_profile_combo()

    def _on_stop(self):
        self.stop_requested.emit()

    # ---------- 外部控制 ----------
    def set_running(self, running: bool):
        self._running = running
        self.stop_btn.setEnabled(running)
        self.conc_spin.setEnabled(not running)
        self.meta_cb.setEnabled(not running)
        self._refresh_start_btn()
        if not running:
            # 跑完后重新扫描,用 singleShot 让 UI 先刷新再扫(大目录下扫 IO 卡)
            QTimer.singleShot(50, self._scan_and_show)

    def set_server_ok(self, ok: bool):
        self._server_ok = ok
        self._refresh_start_btn()

    def _refresh_start_btn(self):
        if self._building_ui:
            return
        self.start_btn.setEnabled(
            bool(self.folder) and not self._running and self._server_ok)
        missing = []
        if not self._server_ok:
            missing.append(tr("task.missing_server"))
        if not self.folder:
            missing.append(tr("task.missing_folder"))
        if self._running:
            self.start_btn.setToolTip(tr("task.tooltip_running"))
        elif missing:
            self.start_btn.setToolTip(tr("task.tooltip_missing", items="、".join(missing)))
        else:
            self.start_btn.setToolTip("")
