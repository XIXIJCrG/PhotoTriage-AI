# -*- coding: utf-8 -*-
"""多张照片并排对比窗口。"""
from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageOps
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .raw_support import HAS_RAWPY, is_raw, load_raw_as_pil
from .utils import score_to_stars


def _load_pixmap(jpg: Path, max_side: int = 1200) -> QPixmap:
    try:
        if is_raw(jpg):
            if not HAS_RAWPY:
                raise RuntimeError("无 rawpy")
            im = load_raw_as_pil(jpg, max_side=max_side)
        else:
            im = Image.open(jpg)
            im = ImageOps.exif_transpose(im)
            im = im.convert("RGB")
            if max(im.size) > max_side:
                im.thumbnail((max_side, max_side), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=86)
        im.close()
        pm = QPixmap()
        pm.loadFromData(buf.getvalue(), "JPEG")
        return pm
    except Exception:  # noqa: BLE001
        return QPixmap()


class _CompareCell(QWidget):
    """一列:大图 + 文件名 + 星级 + 关键指标。"""

    def __init__(self, jpg: Path, row: dict):
        super().__init__()
        self.jpg = jpg
        self.row = row
        self.pm: QPixmap = QPixmap()
        self._loaded = False

        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet("background: #222;")
        self.image_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.image_label.setMinimumSize(QSize(200, 150))

        score = row.get("综合评分", "")
        scene = row.get("场景", "")
        subj = row.get("主体", "") or ""
        self.head = QLabel(f"{jpg.name}")
        self.head.setStyleSheet(
            "font-weight: 600; color: #1F2328; font-size: 13px;")

        self.star = QLabel(f"{score_to_stars(score)}  综合 {score}  {scene}")
        self.star.setStyleSheet("color: #F9A825; font-size: 15px;")

        # 人像四项(如果是人像)
        port_line = ""
        if scene == "人像":
            port_line = (f"神态 {row.get('神态', '')} · 姿态 {row.get('姿态', '')} · "
                         f"眼神 {row.get('眼神', '')} · 美感 {row.get('美感', '')}")
        self.port_label = QLabel(port_line)
        self.port_label.setStyleSheet("color: #6A1B9A; font-size: 12px;")

        self.subj_label = QLabel(subj)
        self.subj_label.setStyleSheet("color: #5A6270; font-size: 12px;")
        self.subj_label.setWordWrap(True)

        self.comment_label = QLabel(row.get("一句话总评", ""))
        self.comment_label.setStyleSheet("color: #1F2328; font-size: 12px;")
        self.comment_label.setWordWrap(True)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(4)
        lay.addWidget(self.image_label, 1)
        lay.addWidget(self.head)
        lay.addWidget(self.star)
        if port_line:
            lay.addWidget(self.port_label)
        lay.addWidget(self.subj_label)
        lay.addWidget(self.comment_label)

    def load(self):
        if self._loaded:
            return
        self._loaded = True
        self.pm = _load_pixmap(self.jpg)
        self._rescale()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._rescale()

    def _rescale(self):
        if self.pm.isNull():
            self.image_label.setText("(无法加载)")
            return
        target = self.image_label.size()
        if target.width() < 10:
            return
        scaled = self.pm.scaled(
            target, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.image_label.setPixmap(scaled)


class CompareWindow(QDialog):
    """最多 4 张并排对比。"""

    def __init__(self, items: list[tuple[Path, dict]], parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"对比 {len(items)} 张")
        self.resize(1600, 900)
        self.setModal(False)
        self.cells: list[_CompareCell] = []

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        for jpg, row in items[:4]:
            cell = _CompareCell(jpg, row)
            lay.addWidget(cell, 1)
            self.cells.append(cell)

    def showEvent(self, event):
        super().showEvent(event)
        # 显示后才知道尺寸,加载一次(load 方法内部有 _loaded 去重)
        for cell in self.cells:
            cell.load()
