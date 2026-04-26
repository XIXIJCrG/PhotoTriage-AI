# -*- coding: utf-8 -*-
"""批处理后台线程。"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from PySide6.QtCore import QThread, Signal

from triage import run_batch


class BatchWorker(QThread):
    """把 triage.run_batch 跑在 QThread 里,通过 Qt signals 汇报进度。

    signals 从内部 ThreadPoolExecutor 的 worker 线程 emit 是安全的,
    Qt 的 AutoConnection 会把跨线程信号排队到主线程处理。
    """

    progress = Signal(object, dict, int, int)   # jpg_path, row, done, total
    log = Signal(str)
    batch_done = Signal(dict)                   # run_batch 返回的 result dict
    batch_failed = Signal(str)                  # 异常消息(只在 run_batch 本身抛时)

    def __init__(
        self,
        folder: Path,
        concurrency: int,
        write_meta: bool = True,
        metadata_mode: str = "embed",
        limit: int = 0,
        skip_processed: bool = True,
        prompt: str | None = None,
        prompt_label: str = "",
        api_url: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        provider_type: str | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.folder = Path(folder)
        self.concurrency = concurrency
        self.write_meta = write_meta
        self.metadata_mode = metadata_mode
        self.limit = limit
        self.skip_processed = skip_processed
        self.prompt = prompt
        self.prompt_label = prompt_label
        self.api_url = api_url
        self.base_url = base_url
        self.model = model
        self.api_key = api_key
        self.provider_type = provider_type
        self._stop_requested = False

    # 外部 API ----------
    def request_stop(self):
        """请求停止。当前批次跑完一张后退出。"""
        self._stop_requested = True
        self.log.emit("收到停止请求,等待当前并发完成…")

    def is_stop_requested(self) -> bool:
        return self._stop_requested

    # QThread 入口 ----------
    def run(self):
        try:
            result: dict[str, Any] = run_batch(
                folder=self.folder,
                concurrency=self.concurrency,
                write_meta=self.write_meta,
                metadata_mode=self.metadata_mode,
                limit=self.limit,
                skip_processed=self.skip_processed,
                prompt=self.prompt,
                prompt_label=self.prompt_label,
                api_url=self.api_url,
                base_url=self.base_url,
                model=self.model,
                api_key=self.api_key,
                provider_type=self.provider_type,
                on_progress=self._on_progress,
                on_log=self._on_log,
                stop_flag=lambda: self._stop_requested,
            )
            self.batch_done.emit(result)
        except Exception as e:  # noqa: BLE001
            self.batch_failed.emit(f"{type(e).__name__}: {e}")

    # 回调 → signal ----------
    def _on_progress(self, jpg: Path, row: dict, done: int, total: int):
        # 注意:此方法可能被内部 ThreadPool 的 worker 线程调用
        self.progress.emit(jpg, row, done, total)

    def _on_log(self, msg: str):
        self.log.emit(msg)
