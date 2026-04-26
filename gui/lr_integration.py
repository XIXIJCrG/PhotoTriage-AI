# -*- coding: utf-8 -*-
"""Lightroom 集成。

能做的:
  - 在 Lightroom 中打开目录(由用户先在设置里填 LR 可执行文件路径)
  - 导出精选列表文件(每行一条:相对路径 + 星级),用户可在 LR 里参考手工 import

不能做(会破坏 LR catalog 所以主动不做):
  - 直接写入 .lrcat 创建 Collection

安抚一下:我们在 analyze 时就把 xmp:Rating 写到 JPG/RAF sidecar,
Lightroom 导入后会自动看到星级,不需要额外步骤。
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from .utils import app_settings


def open_folder_in_lightroom(folder: Path) -> tuple[bool, str]:
    """返回 (success, message)。"""
    exe = app_settings().value("lr/exe", "")
    if not exe or not Path(exe).is_file():
        return False, ("未配置 Lightroom 可执行文件路径,请到"
                       "「设置 → Lightroom」里填一下。")
    try:
        # 注意:LR Classic 的命令行只接受 .lrcat 文件,传目录它不会自动定位。
        # 这里只保证 LR 被启动,用户到 LR 里手动导航或"导入"到该目录即可。
        # XMP 里的星级(xmp:Rating)LR 会自动读出。
        subprocess.Popen([exe])
        return True, ("已启动 Lightroom。LR 不支持从命令行直接打开目录,"
                      "请在 LR 里手动「文件 → 导入」到:\n" + str(folder))
    except Exception as e:  # noqa: BLE001
        return False, f"启动失败: {e}"


def write_picks_list(items: list[tuple[Path, dict]],
                     output: Path) -> int:
    """把精选列表写到一个 UTF-8 文本文件,每行 'relative_path\t星数\t综合分'。
    返回写出的行数。供用户在 LR 中手工参考选片。
    """
    output.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for jpg, row in items:
        score = row.get("综合评分", "")
        try:
            s = float(score)
        except (TypeError, ValueError):
            s = 0
        stars = max(0, min(5,
                    1 if s <= 2 else 2 if s <= 4 else 3 if s <= 6
                    else 4 if s <= 8 else 5))
        lines.append(f"{jpg.name}\t{stars}★\t{score}\t{row.get('一句话总评', '')}")
    output.write_text("\n".join(lines), encoding="utf-8")
    return len(lines)
