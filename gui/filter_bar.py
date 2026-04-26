# -*- coding: utf-8 -*-
"""结果视图的筛选 + 排序工具栏。"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QWidget,
)

from core.i18n import tr

SCENE_CHOICES = [
    ("scene.all", ""),
    ("scene.portrait", "人像"),
    ("scene.street", "街拍"),
    ("scene.landscape", "风光"),
    ("scene.architecture", "建筑"),
    ("scene.still_life", "静物"),
    ("scene.animal", "动物"),
    ("scene.night", "夜景"),
    ("scene.macro", "微距"),
    ("scene.food", "美食"),
    ("scene.event", "活动"),
    ("scene.other", "其他"),
]

SORT_CHOICES = [
    ("sort.overall_desc", "综合评分", False),
    ("sort.overall_asc", "综合评分", True),
    ("sort.aesthetic_desc", "艺术总分", False),
    ("sort.technical_desc", "技术总分", False),
    ("sort.flattering_desc", "美感", False),
    ("sort.expression_desc", "神态", False),
    ("sort.eye_desc", "眼神", False),
    ("sort.composition_desc", "构图", False),
    ("sort.lighting_desc", "光线", False),
    ("sort.filename_asc", "JPG文件名", True),
]


class FilterBar(QWidget):
    """筛选 / 排序栏。

    signals:
      filter_changed()  所有变化都通过这一个信号通知
    """

    filter_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        self._wire()

    def _build_ui(self):
        self.min_spin = QSpinBox()
        self.min_spin.setRange(0, 10)
        self.min_spin.setValue(0)
        self.min_spin.setToolTip(tr("filter.score_min_tip"))

        self.max_spin = QSpinBox()
        self.max_spin.setRange(0, 10)
        self.max_spin.setValue(10)
        self.max_spin.setToolTip(tr("filter.score_max_tip"))

        self.scene_combo = QComboBox()
        for label_key, value in SCENE_CHOICES:
            self.scene_combo.addItem(tr(label_key), value)

        self.has_person_combo = QComboBox()
        self.has_person_combo.addItem(tr("filter.any"), "")
        self.has_person_combo.addItem(tr("filter.has_person"), "是")
        self.has_person_combo.addItem(tr("filter.no_person"), "否")

        self.sort_combo = QComboBox()
        for label_key, _, _ in SORT_CHOICES:
            self.sort_combo.addItem(tr(label_key))

        self.count_label = QLabel("")
        self.count_label.setStyleSheet("color: #666;")

        self.reset_btn = QPushButton(tr("filter.reset"))

        self.group_cb = QCheckBox(tr("filter.group_by_time"))
        self.group_cb.setToolTip(tr("filter.group_by_time_tip"))

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setSpacing(6)
        lay.addWidget(QLabel(tr("filter.score")))
        lay.addWidget(self.min_spin)
        lay.addWidget(QLabel("–"))
        lay.addWidget(self.max_spin)
        lay.addSpacing(12)
        lay.addWidget(QLabel(tr("filter.scene")))
        lay.addWidget(self.scene_combo)
        lay.addSpacing(8)
        lay.addWidget(QLabel(tr("filter.person")))
        lay.addWidget(self.has_person_combo)
        lay.addSpacing(12)
        lay.addWidget(QLabel(tr("filter.sort")))
        lay.addWidget(self.sort_combo)
        lay.addSpacing(12)
        lay.addWidget(self.group_cb)
        lay.addSpacing(8)
        lay.addWidget(self.reset_btn)
        lay.addStretch(1)
        lay.addWidget(self.count_label)

    def _wire(self):
        self.min_spin.valueChanged.connect(self._on_changed)
        self.max_spin.valueChanged.connect(self._on_changed)
        self.scene_combo.currentIndexChanged.connect(self._on_changed)
        self.has_person_combo.currentIndexChanged.connect(self._on_changed)
        self.sort_combo.currentIndexChanged.connect(self._on_changed)
        self.group_cb.toggled.connect(self._on_changed)
        self.reset_btn.clicked.connect(self._on_reset)

    def _on_changed(self, *_):
        # 保证 min <= max
        if self.min_spin.value() > self.max_spin.value():
            self.max_spin.setValue(self.min_spin.value())
        self.filter_changed.emit()

    def _on_reset(self):
        widgets = (self.min_spin, self.max_spin,
                   self.scene_combo, self.has_person_combo, self.sort_combo,
                   self.group_cb)
        for w in widgets:
            w.blockSignals(True)
        self.min_spin.setValue(0)
        self.max_spin.setValue(10)
        self.scene_combo.setCurrentIndex(0)
        self.has_person_combo.setCurrentIndex(0)
        self.sort_combo.setCurrentIndex(0)
        self.group_cb.setChecked(False)
        for w in widgets:
            w.blockSignals(False)
        self.filter_changed.emit()

    def group_by_time(self) -> bool:
        return self.group_cb.isChecked()

    # ---------- getters ----------
    def score_range(self) -> tuple[int, int]:
        return self.min_spin.value(), self.max_spin.value()

    def scene_filter(self) -> str:
        """'' 表示不限。"""
        if self.scene_combo.currentIndex() == 0:
            return ""
        return self.scene_combo.currentData() or ""

    def has_person_filter(self) -> str:
        """'' / '是' / '否'"""
        return self.has_person_combo.currentData() or ""

    def sort_key(self) -> tuple[str, bool]:
        """返回 (column_name, ascending)"""
        idx = self.sort_combo.currentIndex()
        _, col, asc = SORT_CHOICES[idx]
        return col, asc

    def update_count(self, shown: int, total: int):
        self.count_label.setText(tr("filter.count", shown=shown, total=total))
