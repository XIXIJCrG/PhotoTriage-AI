# -*- coding: utf-8 -*-
"""GUI 通用工具。"""
from __future__ import annotations

import hashlib
from pathlib import Path

from PySide6.QtCore import QSettings


def app_settings() -> QSettings:
    """统一的 QSettings 句柄。"""
    return QSettings("PhotoTriage", "GUI")


def score_to_stars(score) -> str:
    """把综合分 (0-10) 转成星级字符串,5 星封顶。"""
    try:
        s = float(score)
    except (TypeError, ValueError):
        return ""
    if s <= 0:
        return ""
    if s <= 2:
        n = 1
    elif s <= 4:
        n = 2
    elif s <= 6:
        n = 3
    elif s <= 8:
        n = 4
    else:
        n = 5
    return "★" * n + "☆" * (5 - n)


def cache_dir_for(folder: Path) -> Path:
    """为某个照片目录返回其缩略图缓存目录。"""
    root = Path.home() / ".triage_cache"
    key = hashlib.sha1(str(folder.resolve()).encode("utf-8")).hexdigest()[:16]
    return root / key


def fmt_duration(seconds: float) -> str:
    """秒 → 人类可读(xx 分 xx 秒)。"""
    if seconds < 60:
        return f"{seconds:.0f}s"
    m, s = divmod(int(seconds), 60)
    if m < 60:
        return f"{m}分{s:02d}秒"
    h, m = divmod(m, 60)
    return f"{h}时{m:02d}分"
