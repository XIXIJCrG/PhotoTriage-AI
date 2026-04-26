# -*- coding: utf-8 -*-
"""进度面板:进度条 + 耗时 + 日志区。"""
from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .utils import fmt_duration


class ProgressPanel(QWidget):
    """实时显示批处理进度的面板。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._start_time: float | None = None
        self._build_ui()
        self.reset()

    def _build_ui(self):
        self.bar = QProgressBar()
        self.bar.setMinimum(0)
        self.bar.setMaximum(100)
        self.bar.setFormat("%p% · %v / %m")

        self.count_label = QLabel("0 / 0")
        self.eta_label = QLabel("")
        self.eta_label.setStyleSheet("color: #666;")

        top = QHBoxLayout()
        top.addWidget(QLabel("进度:"))
        top.addWidget(self.bar, 1)
        top.addSpacing(8)
        top.addWidget(self.eta_label)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setLineWrapMode(QTextEdit.NoWrap)
        # 限制最多 5000 行,防止批量分析几千张后 QTextEdit 吃光内存
        self.log.document().setMaximumBlockCount(5000)
        self.log.setStyleSheet(
            "QTextEdit { font-family: Consolas, 'Courier New', monospace; "
            "font-size: 12px; background: #1e1e1e; color: #d0d0d0; "
            "border: 1px solid #444; }"
        )

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 12)
        lay.setSpacing(6)
        lay.addLayout(top)
        lay.addWidget(self.log, 1)

    # ---------- API ----------
    def reset(self):
        self._start_time = None
        self.bar.setValue(0)
        self.bar.setMaximum(100)
        self.eta_label.setText("")
        self.log.clear()

    def start(self, total: int):
        self._start_time = time.monotonic()
        self.bar.setMaximum(max(1, total))
        self.bar.setValue(0)
        self.eta_label.setText("计算中…")

    def append_log(self, msg: str):
        self.log.append(msg)
        # 自动滚到底
        sb = self.log.verticalScrollBar()
        sb.setValue(sb.maximum())

    def on_progress(self, jpg: Path, row: dict, done: int, total: int):
        self.bar.setMaximum(max(1, total))
        self.bar.setValue(done)
        self._update_eta(done, total)

        score = row.get("综合评分", "")
        scene = row.get("场景", "")
        err = row.get("错误", "")
        subj = row.get("主体") or err or "(无)"
        if err:
            line = f"[!] {jpg.name} → {err}"
        else:
            line = f"  {jpg.name} | 综合 {score} | {scene} | {subj}"
        self.append_log(line)

    def on_done(self, result: dict):
        csv_path = result.get("csv_path")
        processed = result.get("processed", 0)
        failed = result.get("failed", 0)
        skipped = result.get("skipped", 0)
        fatal = result.get("fatal")
        interrupted = result.get("interrupted")

        if self._start_time:
            elapsed = time.monotonic() - self._start_time
            self.eta_label.setText(f"总耗时 {fmt_duration(elapsed)}")

        if fatal:
            self.append_log(f"\n✗ 异常终止: {fatal}")
        elif interrupted:
            self.append_log(f"\n⚠ 已停止,本次新处理 {processed} 张(失败 {failed},跳过 {skipped})")
        else:
            self.append_log(f"\n✓ 完成。新处理 {processed} 张(失败 {failed},跳过 {skipped})")

        if csv_path:
            self.append_log(f"CSV: {csv_path}")

    # ---------- 内部 ----------
    def _update_eta(self, done: int, total: int):
        if not self._start_time or done == 0:
            return
        elapsed = time.monotonic() - self._start_time
        if done >= total:
            self.eta_label.setText(f"用时 {fmt_duration(elapsed)}")
            return
        avg = elapsed / done
        remaining = avg * (total - done)
        self.eta_label.setText(
            f"用时 {fmt_duration(elapsed)} · 剩余 {fmt_duration(remaining)}"
        )
