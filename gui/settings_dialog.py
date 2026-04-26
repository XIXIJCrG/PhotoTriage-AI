# -*- coding: utf-8 -*-
"""应用设置对话框。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from core.i18n import SUPPORTED_LANGUAGES, current_language, set_language, tr
from core.providers import LOCAL_PROVIDER, OPENAI_COMPATIBLE_PROVIDER, chat_completions_url

from triage import API_URL, CONCURRENCY, DEFAULT_BASE_URL, DEFAULT_MODEL, MAX_IMAGE_SIZE

from .styles import mark_primary
from .utils import app_settings


class SettingsDialog(QDialog):
    """统一的设置面板。保存时写回 QSettings。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("settings.title"))
        self.setMinimumWidth(560)
        self._build_ui()
        self._load()

    def _build_ui(self):
        tabs = QTabWidget()

        # --- General ---
        general = QWidget()
        general_lay = QFormLayout(general)
        self.lang_combo = QComboBox()
        for code, label in SUPPORTED_LANGUAGES.items():
            self.lang_combo.addItem(label, code)
        self.lang_hint = QLabel(tr("settings.language_restart"))
        self.lang_hint.setStyleSheet("color: #8A919C;")
        general_lay.addRow(tr("settings.language"), self.lang_combo)
        general_lay.addRow(self.lang_hint)
        tabs.addTab(general, tr("settings.general"))

        # --- 服务器 ---
        srv = QWidget()
        srv_lay = QFormLayout(srv)
        self.provider_combo = QComboBox()
        self.provider_combo.addItem(tr("settings.provider_local"), LOCAL_PROVIDER)
        self.provider_combo.addItem(tr("settings.provider_openai_compatible"), OPENAI_COMPATIBLE_PROVIDER)
        self.base_url_edit = QLineEdit()
        self.base_url_edit.setPlaceholderText(DEFAULT_BASE_URL)
        self.model_edit = QLineEdit()
        self.model_edit.setPlaceholderText(DEFAULT_MODEL)
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.Password)
        self.api_key_edit.setPlaceholderText(tr("settings.api_key_placeholder"))
        self.script_edit = QLineEdit()
        self.script_edit.setPlaceholderText("同目录的 start-triage-server.bat")
        script_row = QWidget()
        script_lay = QHBoxLayout(script_row)
        script_lay.setContentsMargins(0, 0, 0, 0)
        script_lay.setSpacing(4)
        script_lay.addWidget(self.script_edit, 1)
        pick_btn = QPushButton(tr("action.browse"))
        pick_btn.clicked.connect(self._pick_script)
        script_lay.addWidget(pick_btn)
        srv_lay.addRow(tr("settings.provider"), self.provider_combo)
        srv_lay.addRow(tr("settings.base_url"), self.base_url_edit)
        srv_lay.addRow(tr("settings.model"), self.model_edit)
        srv_lay.addRow(tr("settings.api_key"), self.api_key_edit)
        srv_lay.addRow(tr("settings.start_script"), script_row)
        tabs.addTab(srv, tr("settings.server"))

        # --- 分析 ---
        ana = QWidget()
        ana_lay = QFormLayout(ana)
        self.conc_spin = QSpinBox()
        self.conc_spin.setRange(1, 32)
        self.thumb_spin = QSpinBox()
        self.thumb_spin.setRange(128, 1024)
        self.thumb_spin.setSingleStep(32)
        self.thumb_spin.setSuffix(" px")
        self.max_img_spin = QSpinBox()
        self.max_img_spin.setRange(512, 2048)
        self.max_img_spin.setSingleStep(128)
        self.max_img_spin.setSuffix(" px")
        self.meta_cb = QCheckBox(tr("task.write_xmp"))
        self.metadata_mode_combo = QComboBox()
        self.metadata_mode_combo.addItem(tr("settings.metadata_embed"), "embed")
        self.metadata_mode_combo.addItem(tr("settings.metadata_sidecar"), "sidecar")
        ana_lay.addRow(tr("settings.default_concurrency"), self.conc_spin)
        ana_lay.addRow(tr("settings.max_image_side"), self.max_img_spin)
        ana_lay.addRow(tr("settings.thumb_size"), self.thumb_spin)
        ana_lay.addRow("", self.meta_cb)
        ana_lay.addRow(tr("settings.metadata_mode"), self.metadata_mode_combo)
        tabs.addTab(ana, tr("settings.analysis"))

        # --- 评分阈值 ---
        th = QWidget()
        th_lay = QFormLayout(th)
        self.waste_spin = QSpinBox()
        self.waste_spin.setRange(1, 10)
        self.waste_spin.setToolTip(tr("settings.waste_threshold"))
        self.pick_spin = QSpinBox()
        self.pick_spin.setRange(1, 10)
        self.pick_spin.setToolTip(tr("settings.pick_threshold"))
        th_lay.addRow(tr("settings.waste_threshold"), self.waste_spin)
        th_lay.addRow(tr("settings.pick_threshold"), self.pick_spin)
        hint = QLabel(tr("settings.threshold_hint"))
        hint.setStyleSheet("color: #8A919C;")
        th_lay.addRow(hint)
        tabs.addTab(th, tr("settings.thresholds"))

        # --- Lightroom ---
        lr = QWidget()
        lr_lay = QFormLayout(lr)
        self.lr_exe_edit = QLineEdit()
        self.lr_exe_edit.setPlaceholderText(r"C:\Program Files\Adobe\Adobe Lightroom Classic\Lightroom.exe")
        lr_pick_row = QWidget()
        lr_pick_lay = QHBoxLayout(lr_pick_row)
        lr_pick_lay.setContentsMargins(0, 0, 0, 0)
        lr_pick_lay.setSpacing(4)
        lr_pick_lay.addWidget(self.lr_exe_edit, 1)
        lr_pick_btn = QPushButton(tr("action.browse"))
        lr_pick_btn.clicked.connect(self._pick_lr)
        lr_pick_lay.addWidget(lr_pick_btn)
        lr_lay.addRow(tr("settings.lr_exe"), lr_pick_row)
        tabs.addTab(lr, "Lightroom")

        # --- 按钮 ---
        btns = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        mark_primary(btns.button(QDialogButtonBox.Ok))
        btns.accepted.connect(self._save_and_close)
        btns.rejected.connect(self.reject)

        lay = QVBoxLayout(self)
        lay.addWidget(tabs)
        lay.addWidget(btns)

    def _pick_script(self):
        path, _ = QFileDialog.getOpenFileName(
            self, tr("dialog.pick_llama_script"), self.script_edit.text(),
            tr("dialog.batch_scripts"))
        if path:
            self.script_edit.setText(path)

    def _pick_lr(self):
        path, _ = QFileDialog.getOpenFileName(
            self, tr("dialog.pick_lightroom"), self.lr_exe_edit.text(),
            tr("dialog.executables"))
        if path:
            self.lr_exe_edit.setText(path)

    def _load(self):
        s = app_settings()
        provider_type = s.value("provider/type", LOCAL_PROVIDER) or LOCAL_PROVIDER
        idx = self.provider_combo.findData(provider_type)
        self.provider_combo.setCurrentIndex(idx if idx >= 0 else 0)
        idx = self.lang_combo.findData(current_language())
        self.lang_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.base_url_edit.setText(s.value("provider/base_url", DEFAULT_BASE_URL))
        self.model_edit.setText(s.value("provider/model", DEFAULT_MODEL))
        self.api_key_edit.setText(s.value("provider/api_key", ""))
        self.script_edit.setText(s.value("server/script_path", ""))
        try:
            self.conc_spin.setValue(int(s.value("task/concurrency", CONCURRENCY)))
        except (TypeError, ValueError):
            self.conc_spin.setValue(CONCURRENCY)
        try:
            self.thumb_spin.setValue(int(s.value("ui/thumb_size", 256)))
        except (TypeError, ValueError):
            self.thumb_spin.setValue(256)
        try:
            self.max_img_spin.setValue(int(s.value("task/max_image_size", MAX_IMAGE_SIZE)))
        except (TypeError, ValueError):
            self.max_img_spin.setValue(MAX_IMAGE_SIZE)
        self.meta_cb.setChecked(
            bool(s.value("task/write_meta", True, type=bool)))
        metadata_mode = s.value("task/metadata_mode", "embed") or "embed"
        idx = self.metadata_mode_combo.findData(metadata_mode)
        self.metadata_mode_combo.setCurrentIndex(idx if idx >= 0 else 0)
        try:
            self.waste_spin.setValue(int(s.value("ui/waste_threshold", 5)))
        except (TypeError, ValueError):
            self.waste_spin.setValue(5)
        try:
            self.pick_spin.setValue(int(s.value("ui/pick_threshold", 7)))
        except (TypeError, ValueError):
            self.pick_spin.setValue(7)
        self.lr_exe_edit.setText(s.value("lr/exe", ""))

    def _save_and_close(self):
        s = app_settings()
        set_language(self.lang_combo.currentData())
        base_url = self.base_url_edit.text().strip() or DEFAULT_BASE_URL
        model = self.model_edit.text().strip() or DEFAULT_MODEL
        s.setValue("provider/type", self.provider_combo.currentData() or LOCAL_PROVIDER)
        s.setValue("provider/base_url", base_url)
        s.setValue("provider/model", model)
        s.setValue("provider/api_key", self.api_key_edit.text().strip())
        s.setValue("server/api_url", chat_completions_url(base_url) or API_URL)
        s.setValue("server/script_path", self.script_edit.text().strip())
        s.setValue("task/concurrency", int(self.conc_spin.value()))
        s.setValue("ui/thumb_size", int(self.thumb_spin.value()))
        s.setValue("task/max_image_size", int(self.max_img_spin.value()))
        s.setValue("task/write_meta", bool(self.meta_cb.isChecked()))
        s.setValue("task/metadata_mode", self.metadata_mode_combo.currentData())
        s.setValue("ui/waste_threshold", int(self.waste_spin.value()))
        s.setValue("ui/pick_threshold", int(self.pick_spin.value()))
        s.setValue("lr/exe", self.lr_exe_edit.text().strip())
        self.accept()
