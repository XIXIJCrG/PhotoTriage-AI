# -*- coding: utf-8 -*-
"""缩略图网格的专业化卡片绘制 delegate。"""
from __future__ import annotations

from PySide6.QtCore import QRect, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem

from .utils import score_to_stars


CARD_WIDTH = 264
CARD_HEIGHT = 346
THUMB_BOX = 246
PADDING = 7


ROLE_JPG_PATH = Qt.UserRole + 1
ROLE_ROW = Qt.UserRole + 2
ROLE_THUMB = Qt.UserRole + 3
ROLE_EXIF_TIME = Qt.UserRole + 4
ROLE_GROUP_INDEX = Qt.UserRole + 5

GROUP_PALETTE = [
    "#2563EB", "#059669", "#7C3AED", "#EA580C",
    "#0F766E", "#DC2626", "#6D4C41", "#475569",
]


def _score_color(score) -> QColor:
    try:
        s = float(score)
    except (TypeError, ValueError):
        return QColor("#64748B")
    if s >= 8:
        return QColor("#15803D")
    if s >= 7:
        return QColor("#2563EB")
    if s >= 6:
        return QColor("#7C3AED")
    if s >= 5:
        return QColor("#EA580C")
    return QColor("#DC2626")


class PhotoCardDelegate(QStyledItemDelegate):
    """在 QListView IconMode 下绘制缩略图卡片。"""

    def sizeHint(self, option, index) -> QSize:
        return QSize(CARD_WIDTH, CARD_HEIGHT)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index):
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)

        outer = QRectF(option.rect.adjusted(PADDING, PADDING, -PADDING, -PADDING))
        selected = bool(option.state & QStyle.State_Selected)
        hovered = bool(option.state & QStyle.State_MouseOver)

        bg = QColor("#FFFFFF")
        border = QColor("#D9DEE7")
        if selected:
            bg = QColor("#EAF2FF")
            border = QColor("#2563EB")
        elif hovered:
            bg = QColor("#F8FBFF")
            border = QColor("#A9C6F7")

        painter.setPen(QPen(border, 1.2))
        painter.setBrush(bg)
        painter.drawRoundedRect(outer, 8, 8)

        grp = index.data(ROLE_GROUP_INDEX)
        if isinstance(grp, int) and grp >= 0:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(GROUP_PALETTE[grp % len(GROUP_PALETTE)]))
            painter.drawRoundedRect(QRectF(outer.x(), outer.y(), outer.width(), 5), 8, 8)

        image_rect = QRect(
            int(outer.x() + 8), int(outer.y() + 8),
            int(outer.width() - 16), THUMB_BOX,
        )
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#EEF1F5"))
        painter.drawRoundedRect(QRectF(image_rect), 6, 6)

        thumb = index.data(ROLE_THUMB)
        if isinstance(thumb, QPixmap) and not thumb.isNull():
            scaled = thumb.scaled(
                image_rect.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            x = image_rect.x() + (image_rect.width() - scaled.width()) // 2
            y = image_rect.y() + (image_rect.height() - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)
        else:
            painter.setPen(QColor("#94A3B8"))
            painter.drawText(image_rect, Qt.AlignCenter, "加载缩略图…")

        row = index.data(ROLE_ROW) or {}
        score = row.get("综合评分", "")
        scene = row.get("场景", "")
        subject = row.get("主体", "") or row.get("错误", "") or ""
        filename = row.get("JPG文件名", "")
        analysed = bool(str(score).strip())

        text_x = int(outer.x() + 12)
        text_w = int(outer.width() - 24)
        y = image_rect.bottom() + 9

        painter.setFont(option.font)
        fm = painter.fontMetrics()

        if analysed:
            score_text = f"{score_to_stars(score)}  {score}"
            painter.setPen(_score_color(score))
        else:
            score_text = "未分析"
            painter.setPen(QColor("#64748B"))
        score_font = QFont(option.font)
        score_font.setBold(True)
        score_font.setPointSize(score_font.pointSize() + 1)
        painter.setFont(score_font)
        painter.drawText(QRect(text_x, y, text_w, 22), Qt.AlignLeft | Qt.AlignVCenter, score_text)

        pill_text = scene or ("RAW 配对" if row.get("有RAW") == "是" else "照片")
        pill_w = min(82, max(48, fm.horizontalAdvance(pill_text) + 18))
        pill_rect = QRect(int(outer.right() - pill_w - 12), y + 1, pill_w, 20)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#E2E8F0") if not selected else QColor("#D7E8FF"))
        painter.drawRoundedRect(QRectF(pill_rect), 10, 10)
        painter.setPen(QColor("#334155"))
        painter.setFont(option.font)
        painter.drawText(pill_rect, Qt.AlignCenter, pill_text)

        y += 26
        painter.setPen(QColor("#1E293B"))
        subj = subject if analysed else filename
        painter.drawText(
            QRect(text_x, y, text_w, 20),
            Qt.AlignLeft | Qt.AlignVCenter,
            fm.elidedText(subj, Qt.ElideRight, text_w),
        )

        y += 21
        painter.setPen(QColor("#64748B"))
        meta = row.get("拍摄意图", "") if analysed else row.get("RAW文件名", "")
        meta = meta or ("可双击预览原图" if not analysed else "")
        painter.drawText(
            QRect(text_x, y, text_w, 18),
            Qt.AlignLeft | Qt.AlignVCenter,
            fm.elidedText(meta, Qt.ElideRight, text_w),
        )

        painter.restore()
