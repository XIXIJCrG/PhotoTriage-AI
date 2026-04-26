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


SCENE_CHOICES = [
    "(全部)", "人像", "街拍", "风光", "建筑", "静物", "动物",
    "夜景", "微距", "美食", "活动", "其他",
]

SORT_CHOICES = [
    ("综合分 降序", "综合评分", False),
    ("综合分 升序", "综合评分", True),
    ("艺术分 降序", "艺术总分", False),
    ("技术分 降序", "技术总分", False),
    ("美感 降序", "美感", False),
    ("神态 降序", "神态", False),
    ("眼神 降序", "眼神", False),
    ("构图 降序", "构图", False),
    ("光线 降序", "光线", False),
    ("文件名 升序", "JPG文件名", True),
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
        self.min_spin.setToolTip("综合分下限(包含)")

        self.max_spin = QSpinBox()
        self.max_spin.setRange(0, 10)
        self.max_spin.setValue(10)
        self.max_spin.setToolTip("综合分上限(包含)")

        self.scene_combo = QComboBox()
        self.scene_combo.addItems(SCENE_CHOICES)

        self.has_person_combo = QComboBox()
        self.has_person_combo.addItems(["(不限)", "有人", "无人"])

        self.sort_combo = QComboBox()
        for label, _, _ in SORT_CHOICES:
            self.sort_combo.addItem(label)

        self.count_label = QLabel("")
        self.count_label.setStyleSheet("color: #666;")

        self.reset_btn = QPushButton("重置")

        self.group_cb = QCheckBox("按拍摄时间分组")
        self.group_cb.setToolTip("按 EXIF 时间聚类,同场拍摄排一起(60 秒内视为同场)")

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setSpacing(6)
        lay.addWidget(QLabel("分数:"))
        lay.addWidget(self.min_spin)
        lay.addWidget(QLabel("–"))
        lay.addWidget(self.max_spin)
        lay.addSpacing(12)
        lay.addWidget(QLabel("场景:"))
        lay.addWidget(self.scene_combo)
        lay.addSpacing(8)
        lay.addWidget(QLabel("人物:"))
        lay.addWidget(self.has_person_combo)
        lay.addSpacing(12)
        lay.addWidget(QLabel("排序:"))
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
        return self.scene_combo.currentText()

    def has_person_filter(self) -> str:
        """'' / '是' / '否'"""
        idx = self.has_person_combo.currentIndex()
        return "" if idx == 0 else ("是" if idx == 1 else "否")

    def sort_key(self) -> tuple[str, bool]:
        """返回 (column_name, ascending)"""
        idx = self.sort_combo.currentIndex()
        _, col, asc = SORT_CHOICES[idx]
        return col, asc

    def update_count(self, shown: int, total: int):
        self.count_label.setText(f"{shown} / {total} 张")
