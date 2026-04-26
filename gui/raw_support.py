# -*- coding: utf-8 -*-
"""RAW 文件解码支持(rawpy)。

设计思路:
  - 生成缩略图优先用 embedded JPEG 预览(极快,Fuji RAF 通常带全尺寸预览)
  - 解不出来 fallback 到 postprocess 全解(慢但一定能出图)
  - 预览窗口大图:同上
"""
from __future__ import annotations

import io
from pathlib import Path

from PIL import Image

try:
    import rawpy  # type: ignore
    HAS_RAWPY = True
except Exception:  # noqa: BLE001
    HAS_RAWPY = False


RAW_EXTS = {".raf", ".arw", ".cr2", ".cr3", ".nef", ".dng", ".orf",
            ".pef", ".rw2", ".srw"}


def is_raw(path: Path) -> bool:
    return path.suffix.lower() in RAW_EXTS


def load_raw_as_pil(path: Path, max_side: int | None = None) -> Image.Image:
    """读 RAW 返回 PIL Image(RGB)。优先用 embedded JPEG 预览。

    max_side 给定时,会把 embedded 预览按比例缩到该尺寸以内。
    """
    if not HAS_RAWPY:
        raise RuntimeError("需要 rawpy: pip install rawpy")

    with rawpy.imread(str(path)) as raw:
        try:
            thumb = raw.extract_thumb()
        except rawpy.LibRawNoThumbnailError:
            thumb = None

        if thumb is not None and thumb.format == rawpy.ThumbFormat.JPEG:
            im = Image.open(io.BytesIO(thumb.data))
            im.load()
            im = im.convert("RGB")
            if max_side and max(im.size) > max_side:
                im.thumbnail((max_side, max_side), Image.LANCZOS)
            return im
        if thumb is not None and thumb.format == rawpy.ThumbFormat.BITMAP:
            im = Image.fromarray(thumb.data)
            if max_side and max(im.size) > max_side:
                im.thumbnail((max_side, max_side), Image.LANCZOS)
            return im

        # 没 embedded preview,走 postprocess(慢但保底)
        rgb = raw.postprocess(use_camera_wb=True, half_size=True,
                              no_auto_bright=False, output_bps=8)
        im = Image.fromarray(rgb)
        if max_side and max(im.size) > max_side:
            im.thumbnail((max_side, max_side), Image.LANCZOS)
        return im
