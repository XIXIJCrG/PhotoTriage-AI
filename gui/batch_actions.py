# -*- coding: utf-8 -*-
"""批量操作:一键淘汰、导出精选、打开 CSV、撤销。

核心数据结构是 ResultsView 提供的 (jpg_path, row_dict) 列表;
本模块只负责:
  - 移动文件(淘汰)
  - 拷贝文件(导出)
  - 生成撤销记录

UI 部分(BatchActionsBar)负责发信号,不直接改文件。
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)


DISCARD_SUBDIR = "_废片"


@dataclass
class FileMove:
    """一次文件移动记录(用于撤销)。"""
    src: Path       # 原始位置
    dst: Path       # 移动后位置


@dataclass
class DiscardRecord:
    """一次淘汰批次,保存能完整撤销所需的信息。"""
    moves: list[FileMove] = field(default_factory=list)
    rows: list[tuple[Path, dict]] = field(default_factory=list)  # (原 jpg 路径, row dict)
    skipped: list[Path] = field(default_factory=list)  # 因目标冲突被跳过的 JPG

    def is_empty(self) -> bool:
        return not self.moves and not self.rows


def _safe_move(src: Path, dst_dir: Path) -> Path | None:
    """把 src 移动到 dst_dir 下同名位置。
    dst 已存在则跳过(返回 None)。成功返回新路径。"""
    if not src.is_file():
        return None
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / src.name
    if dst.exists():
        return None
    try:
        shutil.move(str(src), str(dst))
    except OSError:
        return None
    return dst


def _safe_copy(src: Path, dst_dir: Path) -> Path | None:
    if not src.is_file():
        return None
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / src.name
    if dst.exists():
        return None
    try:
        shutil.copy2(str(src), str(dst))
    except OSError:
        return None
    return dst


def _related_files(jpg_path: Path, row: dict, folder: Path) -> list[Path]:
    """一张照片相关的所有物理文件(JPG + 配对 RAW + 对应 xmp sidecar)。
    按去重后的顺序返回;只包括当前实际存在的文件。"""
    out: list[Path] = []
    seen: set[Path] = set()

    def add(p: Path):
        if p.is_file() and p not in seen:
            seen.add(p)
            out.append(p)

    add(jpg_path)
    raw_name = row.get("RAW文件名", "") if isinstance(row, dict) else ""
    if raw_name:
        raw_src = folder / raw_name
        add(raw_src)
        # RAW stem 的 .xmp(Lightroom / C1 标准 sidecar)
        add(folder / (Path(raw_name).stem + ".xmp"))
    # JPG 同名 .xmp(罕见,一般不与 RAW 同 stem)
    add(jpg_path.with_suffix(".xmp"))
    return out


def discard_files(
    items: Iterable[tuple[Path, dict]],
    folder: Path,
) -> DiscardRecord:
    """把 items 里所有 JPG 以及配对的 RAF / XMP sidecar 移动到 folder/_废片/。

    冲突策略:**整组跳过**。如果同一张照片的 JPG / RAF / XMP 任一个目标已存在,
    整组都不动,避免出现"JPG 搬走 RAF 留下"的孤儿。

    返回 DiscardRecord。
    """
    record = DiscardRecord()
    discard_dir = folder / DISCARD_SUBDIR

    for jpg_path, row in items:
        if not jpg_path.is_file():
            continue

        # 先把这一组要搬的文件找出来
        related = _related_files(jpg_path, row if isinstance(row, dict) else {}, folder)
        if not related:
            continue

        # 冲突预检:有一个目标已存在就整组跳过
        discard_dir.mkdir(parents=True, exist_ok=True)
        conflict = any((discard_dir / p.name).exists() for p in related)
        if conflict:
            record.skipped.append(jpg_path)
            continue

        # 先把 row 记录下来(不论移动成败,用户看到这一条进过流程)
        record.rows.append((jpg_path, dict(row) if isinstance(row, dict) else {}))

        # 真正搬
        for src in related:
            moved = _safe_move(src, discard_dir)
            if moved is not None:
                record.moves.append(FileMove(src, moved))

    return record


def undo_discard(record: DiscardRecord) -> int:
    """反向执行 record 里的移动。返回成功还原的文件数。"""
    restored = 0
    for mv in reversed(record.moves):
        if not mv.dst.is_file():
            continue
        if mv.src.exists():
            # 原位置已经有东西了(被别的任务填了?),不强行覆盖
            continue
        try:
            shutil.move(str(mv.dst), str(mv.src))
            restored += 1
        except OSError:
            pass
    return restored


def export_files(
    items: Iterable[tuple[Path, dict]],
    folder: Path,
    dest: Path,
    include_raw: bool = True,
) -> tuple[int, int]:
    """把 items 里的 JPG(可选 + RAF)复制到 dest。

    返回 (jpg_count, raw_count)。冲突跳过。
    """
    jpg_count = 0
    raw_count = 0
    for jpg_path, row in items:
        if not jpg_path.is_file():
            continue
        if _safe_copy(jpg_path, dest) is not None:
            jpg_count += 1
        if include_raw and isinstance(row, dict):
            raw_name = row.get("RAW文件名", "")
            if raw_name:
                raw_src = folder / raw_name
                if _safe_copy(raw_src, dest) is not None:
                    raw_count += 1
    return jpg_count, raw_count


# ---------- UI ----------

class BatchActionsBar(QWidget):
    """批量操作工具条。发 signal,不直接操作文件。"""

    discard_requested = Signal()
    export_requested = Signal()
    compare_requested = Signal()
    open_csv_requested = Signal()
    show_in_explorer_requested = Signal()
    undo_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        self.set_selection_count(0)
        self.set_undo_available(False)

    def _build_ui(self):
        self.count_label = QLabel("")
        self.count_label.setStyleSheet("color: #555;")

        self.discard_btn = QPushButton("淘汰选中")
        self.discard_btn.setToolTip("把选中的照片连同 RAF/XMP 移到 _废片/ 子目录(可撤销)")
        self.discard_btn.setStyleSheet(
            "QPushButton { padding: 4px 12px; }"
            "QPushButton:enabled { color: #B71C1C; }"
        )

        self.export_btn = QPushButton("导出选中…")
        self.export_btn.setToolTip("把选中的照片(连同 RAF)复制到指定目录")

        self.compare_btn = QPushButton("对比")
        self.compare_btn.setToolTip("选中 2-4 张,并排大图对比")

        self.undo_btn = QPushButton("撤销上次淘汰")
        self.undo_btn.setToolTip("把 _废片/ 里最近一次移动的文件还原回原位置")

        self.open_csv_btn = QPushButton("打开 CSV")
        self.open_csv_btn.setToolTip("用系统默认程序(通常是 Excel)打开本目录最新的 triage CSV")

        self.explorer_btn = QPushButton("资源管理器")
        self.explorer_btn.setToolTip("在资源管理器中打开当前目录")

        self.discard_btn.clicked.connect(self.discard_requested)
        self.export_btn.clicked.connect(self.export_requested)
        self.compare_btn.clicked.connect(self.compare_requested)
        self.undo_btn.clicked.connect(self.undo_requested)
        self.open_csv_btn.clicked.connect(self.open_csv_requested)
        self.explorer_btn.clicked.connect(self.show_in_explorer_requested)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 4, 10, 4)
        lay.setSpacing(6)
        lay.addWidget(self.count_label)
        lay.addStretch(1)
        lay.addWidget(self.undo_btn)
        lay.addSpacing(8)
        lay.addWidget(self.compare_btn)
        lay.addWidget(self.discard_btn)
        lay.addWidget(self.export_btn)
        lay.addSpacing(8)
        lay.addWidget(self.open_csv_btn)
        lay.addWidget(self.explorer_btn)

    def set_selection_count(self, n: int):
        if n == 0:
            self.count_label.setText("未选中")
            self.discard_btn.setEnabled(False)
            self.export_btn.setEnabled(False)
            self.compare_btn.setEnabled(False)
        else:
            self.count_label.setText(f"已选中 {n} 张")
            self.discard_btn.setEnabled(True)
            self.export_btn.setEnabled(True)
            self.compare_btn.setEnabled(2 <= n <= 4)
            if n > 4:
                self.compare_btn.setToolTip("对比最多支持 4 张")
            else:
                self.compare_btn.setToolTip("选中 2-4 张,并排大图对比")

    def set_undo_available(self, ok: bool):
        self.undo_btn.setEnabled(ok)

    def set_folder_available(self, ok: bool):
        """当前是否有 folder(没有就禁用打开 CSV / 资源管理器)。"""
        self.open_csv_btn.setEnabled(ok)
        self.explorer_btn.setEnabled(ok)
