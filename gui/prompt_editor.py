# -*- coding: utf-8 -*-
"""Prompt profile 编辑对话框。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from core.i18n import tr

from .prompt_manager import DEFAULT_PROFILE_NAME, PromptStore
from .styles import mark_danger, mark_primary


class PromptEditorDialog(QDialog):
    """左侧 profile 列表 + 右侧编辑。默认 profile 只读。"""

    def __init__(self, store: PromptStore, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("prompt_editor.title"))
        self.resize(1000, 720)
        self.store = store
        self._build_ui()
        self._refresh_list()

    def _build_ui(self):
        # 左侧
        left = QWidget()
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(0, 0, 0, 0)
        self.list = QListWidget()
        self.list.currentItemChanged.connect(lambda item, _prev: self._on_select(
            item.data(Qt.UserRole) if item else ""))

        btn_row = QHBoxLayout()
        self.new_btn = QPushButton(tr("prompt_editor.new"))
        self.dup_btn = QPushButton(tr("prompt_editor.duplicate"))
        self.del_btn = QPushButton(tr("prompt_editor.delete"))
        mark_danger(self.del_btn)
        self.new_btn.clicked.connect(self._new_profile)
        self.dup_btn.clicked.connect(self._dup_profile)
        self.del_btn.clicked.connect(self._delete_profile)
        btn_row.addWidget(self.new_btn)
        btn_row.addWidget(self.dup_btn)
        btn_row.addWidget(self.del_btn)

        left_lay.addWidget(QLabel("Profiles"))
        left_lay.addWidget(self.list, 1)
        left_lay.addLayout(btn_row)

        # 右侧
        right = QWidget()
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(0, 0, 0, 0)

        self.name_label = QLabel("")
        self.name_label.setStyleSheet(
            "font-size: 14px; font-weight: 600; color: #1976D2;")

        self.editor = QPlainTextEdit()
        mono = QFont("Consolas", 10)
        self.editor.setFont(mono)
        self.editor.setStyleSheet(
            "QPlainTextEdit { background: #FFFFFF; color: #1F2328;"
            " border: 1px solid #E0E3E8; padding: 6px; }")
        self.editor.setTabChangesFocus(False)

        self.hint = QLabel(tr("prompt_editor.hint"))
        self.hint.setWordWrap(True)
        self.hint.setStyleSheet("color: #8A919C; font-size: 12px;")

        self.save_btn = QPushButton(tr("prompt_editor.save"))
        mark_primary(self.save_btn)
        self.save_btn.clicked.connect(self._save_current)

        right_lay.addWidget(self.name_label)
        right_lay.addWidget(self.editor, 1)
        right_lay.addWidget(self.hint)
        save_row = QHBoxLayout()
        save_row.addStretch(1)
        save_row.addWidget(self.save_btn)
        right_lay.addLayout(save_row)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([220, 760])

        btns = QDialogButtonBox(QDialogButtonBox.Close)
        btns.rejected.connect(self.reject)

        lay = QVBoxLayout(self)
        lay.addWidget(splitter, 1)
        lay.addWidget(btns)

    # ---------- 列表 ----------
    def _refresh_list(self, select: str | None = None):
        self.list.blockSignals(True)
        self.list.clear()
        names = self.store.list_names()
        for n in names:
            display = tr("prompt.default") if n == DEFAULT_PROFILE_NAME else n
            item = QListWidgetItem(display)
            item.setData(Qt.UserRole, n)
            self.list.addItem(item)
        target = select if select in names else (names[0] if names else "")
        if target:
            for i in range(self.list.count()):
                item = self.list.item(i)
                if item.data(Qt.UserRole) == target:
                    self.list.setCurrentItem(item)
                    break
        self.list.blockSignals(False)
        self._on_select(target)

    def _on_select(self, name: str):
        if not name:
            self.editor.setPlainText("")
            self.name_label.setText("")
            self.save_btn.setEnabled(False)
            self.del_btn.setEnabled(False)
            return
        profile = self.store.get(name)
        if profile is None:
            return
        self.name_label.setText(name + (tr("prompt_editor.default_readonly") if name == DEFAULT_PROFILE_NAME else ""))
        self.editor.setPlainText(profile.prompt)
        is_default = (name == DEFAULT_PROFILE_NAME)
        self.editor.setReadOnly(is_default)
        self.save_btn.setEnabled(not is_default)
        self.del_btn.setEnabled(not is_default)

    # ---------- 操作 ----------
    def _new_profile(self):
        name, ok = QInputDialog.getText(
            self, tr("prompt_editor.new_title"), tr("prompt_editor.name_label"))
        if not ok or not name.strip():
            return
        name = name.strip()
        if name == DEFAULT_PROFILE_NAME:
            QMessageBox.warning(self, tr("prompt_editor.name_conflict"), tr("prompt_editor.default_name_forbidden"))
            return
        if self.store.get(name) is not None:
            QMessageBox.warning(self, tr("prompt_editor.name_conflict"), tr("prompt_editor.name_exists"))
            return
        default_prompt = self.store.get(DEFAULT_PROFILE_NAME).prompt
        self.store.upsert(name, default_prompt)
        self._refresh_list(select=name)

    def _dup_profile(self):
        cur = self.list.currentItem()
        if cur is None:
            return
        src_name = cur.data(Qt.UserRole) or cur.text()
        base = self.store.get(src_name)
        if base is None:
            return
        new_name, ok = QInputDialog.getText(
            self, tr("prompt_editor.copy_title"), tr("prompt_editor.new_name_label"),
            text=f"{src_name}{tr('prompt_editor.copy_suffix')}")
        if not ok or not new_name.strip():
            return
        new_name = new_name.strip()
        if new_name == DEFAULT_PROFILE_NAME or self.store.get(new_name):
            QMessageBox.warning(self, tr("prompt_editor.name_conflict"), tr("prompt_editor.name_exists"))
            return
        self.store.upsert(new_name, base.prompt)
        self._refresh_list(select=new_name)

    def _delete_profile(self):
        cur = self.list.currentItem()
        if cur is None:
            return
        name = cur.data(Qt.UserRole) or cur.text()
        if name == DEFAULT_PROFILE_NAME:
            return
        reply = QMessageBox.question(
            self, tr("prompt_editor.delete_confirm"),
            tr("prompt_editor.delete_confirm_body", name=name),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        self.store.delete(name)
        self._refresh_list()

    def _save_current(self):
        cur = self.list.currentItem()
        if cur is None:
            return
        name = cur.data(Qt.UserRole) or cur.text()
        if name == DEFAULT_PROFILE_NAME:
            return
        self.store.upsert(name, self.editor.toPlainText())
        QMessageBox.information(self, tr("prompt_editor.saved"), tr("prompt_editor.saved_body", name=name))
