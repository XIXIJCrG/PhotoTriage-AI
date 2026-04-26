# -*- coding: utf-8 -*-
"""按拍摄时间聚类(同场拍摄分组)。

从 JPG EXIF 读 DateTimeOriginal,相邻照片间隔 ≤ gap_seconds 视为同一组。
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Iterable

from PIL import Image


def read_capture_time(jpg: Path) -> datetime | None:
    """尝试从 EXIF 读取拍摄时间。失败返回 None。
    兼容 'YYYY:MM:DD HH:MM:SS' 及尾部带时区/毫秒等变体。"""
    try:
        with Image.open(jpg) as im:
            ex = im.getexif()
            for tag in (0x9003, 0x0132):  # DateTimeOriginal, DateTime
                v = ex.get(tag)
                if not v:
                    continue
                # 去掉可能的时区/毫秒尾巴,只留前 19 字符 YYYY:MM:DD HH:MM:SS
                s = str(v).strip()[:19]
                try:
                    return datetime.strptime(s, "%Y:%m:%d %H:%M:%S")
                except ValueError:
                    continue
    except Exception:  # noqa: BLE001
        pass
    return None


def group_by_time(
    items: list[tuple[Path, dict]],
    gap_seconds: int = 60,
) -> list[list[tuple[Path, dict]]]:
    """把 items 按 EXIF 时间聚类成若干组。

    逻辑:
      - 先按时间升序排
      - 相邻两张差 > gap 秒就开新组
      - 没有时间的单独成一组(排在最后)
    """
    with_time: list[tuple[datetime, Path, dict]] = []
    without_time: list[tuple[Path, dict]] = []
    for jpg, row in items:
        t = read_capture_time(jpg)
        if t is None:
            without_time.append((jpg, row))
        else:
            with_time.append((t, jpg, row))

    with_time.sort(key=lambda x: x[0])

    groups: list[list[tuple[Path, dict]]] = []
    current: list[tuple[Path, dict]] = []
    last_t: datetime | None = None
    for t, jpg, row in with_time:
        if last_t is None or (t - last_t).total_seconds() <= gap_seconds:
            current.append((jpg, row))
        else:
            if current:
                groups.append(current)
            current = [(jpg, row)]
        last_t = t
    if current:
        groups.append(current)

    if without_time:
        groups.append(without_time)

    return groups
