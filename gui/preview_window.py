# -*- coding: utf-8 -*-
"""照片大图预览窗口。"""
from __future__ import annotations

import io
import os
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageOps
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QAction, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .utils import score_to_stars


METADATA_ORDER = [
    # 标题栏 / 基础
    ("JPG文件名", "文件名"),
    ("RAW文件名", "RAW"),
    # 综合
    ("综合评分", "综合评分"),
    ("技术总分", "技术总分"),
    ("艺术总分", "艺术总分"),
    # 内容
    ("场景", "场景"),
    ("拍摄意图", "拍摄意图"),
    ("主体", "主体"),
    ("画面感受", "画面感受"),
    ("有人", "有人"),
    ("人数", "人数"),
    ("时段", "时段"),
    ("主色调", "主色调"),
    # 技术
    ("对焦", "对焦"),
    ("曝光", "曝光"),
    ("噪点", "噪点"),
    ("白平衡", "白平衡"),
    ("动态模糊", "动态模糊"),
    ("动态模糊是否有意", "动态模糊是否有意"),
    # 艺术
    ("构图", "构图"),
    ("光线", "光线"),
    ("色彩", "色彩"),
    ("主体突出", "主体突出"),
    ("叙事感", "叙事感"),
    ("独特性", "独特性"),
    # 人像
    ("神态", "神态"),
    ("姿态", "姿态"),
    ("眼神", "眼神"),
    ("美感", "美感"),
    ("人像点评", "人像点评"),
    # 总评
    ("优点", "优点"),
    ("问题", "问题"),
    ("一句话总评", "一句话总评"),
    # 元信息
    ("耗时秒", "分析耗时"),
    ("错误", "错误"),
]


def open_in_system(path: Path) -> None:
    """用系统默认程序打开。"""
    if sys.platform == "win32":
        os.startfile(str(path))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


def show_in_explorer(path: Path) -> None:
    """在资源管理器中显示并选中。"""
    if sys.platform == "win32":
        subprocess.Popen(["explorer", "/select,", str(path)])
    elif sys.platform == "darwin":
        subprocess.Popen(["open", "-R", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path.parent)])


class PreviewWindow(QDialog):
    """显示原图 + 完整元数据。支持上一张/下一张浏览。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("预览")
        self.resize(1400, 900)
        self.setModal(False)

        self.items: list[tuple[Path, dict]] = []
        self.index = 0
        self._orig_pm: QPixmap | None = None  # 原始 pixmap 用于 resize 重 scale
        self._build_ui()
        self._wire_shortcuts()

    def _build_ui(self):
        # 左侧大图
        self.image_label = QLabel("")
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet("background: #222;")
        self.image_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.image_label.setMinimumSize(QSize(400, 300))

        scroll = QScrollArea()
        scroll.setWidget(self.image_label)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background: #222; border: none;")

        # 右侧元数据面板
        right = QWidget()
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(12, 12, 12, 12)
        right_lay.setSpacing(8)

        self.title_label = QLabel("")
        self.title_label.setStyleSheet(
            "QLabel { font-size: 16px; font-weight: 600; color: #1F2328; "
            "padding: 2px 0; }")
        self.title_label.setWordWrap(True)

        self.star_label = QLabel("")
        self.star_label.setStyleSheet(
            "QLabel { font-size: 22px; color: #F9A825; padding: 2px 0; }")

        # 大文本框展示所有字段 — 明确的深色文字保证夜间主题下也能看清
        self.meta_text = QTextEdit()
        self.meta_text.setReadOnly(True)
        self.meta_text.setFocusPolicy(Qt.NoFocus)
        self.meta_text.setStyleSheet(
            "QTextEdit {"
            " background: #FFFFFF;"
            " color: #1F2328;"
            " border: 1px solid #E0E3E8;"
            " border-radius: 4px;"
            " font-family: 'Microsoft YaHei UI', 'Microsoft YaHei', 'Segoe UI', sans-serif;"
            " font-size: 13px;"
            " padding: 4px;"
            " }"
        )

        # 操作按钮
        btns = QHBoxLayout()
        self.prev_btn = QPushButton("◀ 上一张")
        self.next_btn = QPushButton("下一张 ▶")
        self.explorer_btn = QPushButton("在资源管理器中显示")
        self.open_btn = QPushButton("用默认程序打开")
        btns.addWidget(self.prev_btn)
        btns.addWidget(self.next_btn)
        btns.addStretch(1)
        btns.addWidget(self.explorer_btn)
        btns.addWidget(self.open_btn)

        right_lay.addWidget(self.title_label)
        right_lay.addWidget(self.star_label)
        right_lay.addWidget(self.meta_text, 1)
        right_lay.addLayout(btns)

        # Splitter 左右可拖
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.addWidget(scroll)
        self.splitter.addWidget(right)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)
        self.splitter.setSizes([900, 500])

        main_lay = QVBoxLayout(self)
        main_lay.setContentsMargins(0, 0, 0, 0)
        main_lay.addWidget(self.splitter)

        self.prev_btn.clicked.connect(self.show_prev)
        self.next_btn.clicked.connect(self.show_next)
        self.explorer_btn.clicked.connect(self._on_explorer)
        self.open_btn.clicked.connect(self._on_open)

    def _wire_shortcuts(self):
        act_prev = QAction(self)
        act_prev.setShortcut("Left")
        act_prev.triggered.connect(self.show_prev)
        self.addAction(act_prev)

        act_next = QAction(self)
        act_next.setShortcut("Right")
        act_next.triggered.connect(self.show_next)
        self.addAction(act_next)

        act_close = QAction(self)
        act_close.setShortcut("Esc")
        act_close.triggered.connect(self.close)
        self.addAction(act_close)

    # ---------- API ----------
    def show_list(self, items: list[tuple[Path, dict]], start_index: int):
        if not items:
            self.items = []
            self.index = 0
            self._orig_pm = None
            self.image_label.setPixmap(QPixmap())
            self.image_label.setText("(无可显示项)")
            self.title_label.setText("")
            self.star_label.setText("")
            self.meta_text.clear()
            return
        self.items = items
        self.index = max(0, min(start_index, len(items) - 1))
        self._refresh()

    def show_prev(self):
        if not self.items:
            return
        if self.index > 0:
            self.index -= 1
            self._refresh()

    def show_next(self):
        if not self.items:
            return
        if self.index < len(self.items) - 1:
            self.index += 1
            self._refresh()

    # ---------- 内部 ----------
    def _current(self) -> tuple[Path, dict] | None:
        if not self.items:
            return None
        return self.items[self.index]

    def _refresh(self):
        cur = self._current()
        if not cur:
            return
        jpg, row = cur
        self.setWindowTitle(f"预览 — {jpg.name}  ({self.index + 1}/{len(self.items)})")

        score = row.get("综合评分", "")
        self.title_label.setText(
            f"{jpg.name}   综合 {score}   {row.get('场景', '')}"
        )
        self.star_label.setText(score_to_stars(score))

        # 加载图片
        self._load_image(jpg)

        # 元数据
        self.meta_text.setHtml(self._row_to_html(row))

        # 按钮状态
        self.prev_btn.setEnabled(self.index > 0)
        self.next_btn.setEnabled(self.index < len(self.items) - 1)

    def _load_image(self, jpg: Path):
        from .raw_support import HAS_RAWPY, is_raw, load_raw_as_pil
        try:
            if is_raw(jpg):
                if not HAS_RAWPY:
                    raise RuntimeError("需要安装 rawpy 才能预览 RAW 文件")
                im = load_raw_as_pil(jpg, max_side=1800)
            else:
                im = Image.open(jpg)
                im = ImageOps.exif_transpose(im)
                im = im.convert("RGB")
                max_side = 1800
                if max(im.size) > max_side:
                    im.thumbnail((max_side, max_side), Image.LANCZOS)
            buf = io.BytesIO()
            im.save(buf, format="JPEG", quality=88)
            im.close()
            pm = QPixmap()
            pm.loadFromData(buf.getvalue(), "JPEG")
            if pm.isNull():
                raise ValueError("pixmap 加载失败")
        except Exception as e:  # noqa: BLE001
            self._orig_pm = None
            self.image_label.setPixmap(QPixmap())
            self.image_label.setText(f"无法加载图片:\n{e}")
            return

        self._orig_pm = pm
        self._rescale_image()

    def _rescale_image(self):
        if self._orig_pm is None or self._orig_pm.isNull():
            return
        viewport = self.image_label.parentWidget().size()
        if viewport.width() < 10 or viewport.height() < 10:
            viewport = self.image_label.size()
        scaled = self._orig_pm.scaled(
            viewport, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.image_label.setPixmap(scaled)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._rescale_image()

    def showEvent(self, event):
        super().showEvent(event)
        # 首次显示时 viewport 尺寸已就绪,重新 scale 一次
        self._rescale_image()

    def _row_to_html(self, row: dict) -> str:
        lines = ["<html><body style='color:#1F2328;'>",
                "<table style='border-collapse:collapse; width:100%;'>"]
        for key, label in METADATA_ORDER:
            v = row.get(key, "")
            if v == "" or v is None:
                continue
            is_key = key in ("综合评分", "技术总分", "艺术总分",
                             "神态", "姿态", "眼神", "美感",
                             "优点", "问题", "一句话总评")
            bg = "#FFF3E0" if is_key else "#FFFFFF"
            val_color = "#B71C1C" if key == "错误" else "#1F2328"
            lines.append(
                f"<tr style='background:{bg};'>"
                f"<td style='padding:6px 10px; color:#5A6270; font-weight:500;"
                f" vertical-align:top; width:100px;'>{label}</td>"
                f"<td style='padding:6px 10px; color:{val_color};'>"
                f"{_escape(v)}</td></tr>"
            )
        lines.append("</table></body></html>")
        return "".join(lines)

    def _on_explorer(self):
        cur = self._current()
        if cur:
            show_in_explorer(cur[0])

    def _on_open(self):
        cur = self._current()
        if cur:
            open_in_system(cur[0])


def _escape(v) -> str:
    s = str(v)
    return (s.replace("&", "&amp;").replace("<", "&lt;")
             .replace(">", "&gt;").replace("|", " · "))
