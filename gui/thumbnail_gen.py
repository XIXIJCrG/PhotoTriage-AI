# -*- coding: utf-8 -*-
"""后台缩略图生成器。

从 JPG/PNG 原图生成 256px 的缩略图,存到缓存目录。
已经存在的直接跳过。通过 Qt signal 报告进度。
"""
from __future__ import annotations

import hashlib
import os
import queue
import threading
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path
from typing import Optional

from PIL import Image, ImageOps
from PySide6.QtCore import QObject, QThread, Signal

from .raw_support import HAS_RAWPY, is_raw, load_raw_as_pil
from .utils import cache_dir_for

THUMB_SIZE = 256
THUMB_QUALITY = 78
THUMB_WORKERS = max(2, min(4, (os.cpu_count() or 2) // 2))


def make_thumbnail(src: Path, dst: Path, size: int = THUMB_SIZE) -> None:
    """同步生成单张缩略图。支持 JPG/PNG 以及 RAW(需要 rawpy)。"""
    dst.parent.mkdir(parents=True, exist_ok=True)
    if is_raw(src):
        if not HAS_RAWPY:
            raise RuntimeError(f"RAW 缩略图需要 rawpy: {src.name}")
        im = load_raw_as_pil(src, max_side=size * 2)
    else:
        im = Image.open(src)
        # JPEG 可先让解码器走低分辨率 draft,大图生成缩略图时会少解很多像素。
        try:
            im.draft("RGB", (size * 2, size * 2))
        except Exception:
            pass
        im = ImageOps.exif_transpose(im)
        if im.mode != "RGB":
            im = im.convert("RGB")
    try:
        im.thumbnail((size, size), Image.LANCZOS)
        # optimize=True 会明显吃 CPU;缩略图缓存更看重吞吐,文件大一点没关系。
        im.save(dst, format="JPEG", quality=THUMB_QUALITY, optimize=False)
    finally:
        try:
            im.close()
        except Exception:
            pass


def thumb_path_for(folder: Path, src: Path) -> Path:
    """某文件夹下某张照片的缩略图缓存路径。

    缓存名包含完整文件名、大小和修改时间,避免 A.JPG/A.PNG/A.RAF
    这类同名不同格式照片误用同一张缩略图。
    """
    stat = src.stat() if src.exists() else None
    stamp = f"{stat.st_size}-{stat.st_mtime_ns}" if stat else "missing"
    key = f"{src.name}|{stamp}".encode("utf-8", errors="surrogatepass")
    digest = hashlib.blake2b(key, digest_size=8).hexdigest()
    return cache_dir_for(folder) / f"{src.stem}-{digest}.jpg"


class ThumbnailGenerator(QThread):
    """持续消费任务队列,后台生成缩略图。

    - 通过 enqueue(jpg_path, folder) 追加任务(线程安全)
    - 生成完毕 emit thumb_ready(jpg_path, cache_path)
    - 失败 emit thumb_failed(jpg_path, err_msg)
    - stop() 让线程尽快退出
    """

    thumb_ready = Signal(object, object)    # jpg_path, cache_path(Path)
    thumb_failed = Signal(object, str)
    exif_time_ready = Signal(object, object)  # jpg_path, datetime 或 None
    idle = Signal()                         # 队列为空时发一次

    def __init__(self, parent: Optional[QObject] = None, workers: int = THUMB_WORKERS):
        super().__init__(parent)
        self._queue: "queue.Queue[tuple[Path, Path] | None]" = queue.Queue()
        self._stop = threading.Event()
        self._seen: set[Path] = set()
        self._seen_lock = threading.Lock()
        self._workers = max(1, workers)

    # ---------- 外部 API ----------
    def enqueue(self, src: Path, folder: Path) -> Path:
        """加入队列,返回将来的缓存路径(不保证已存在)。
        已经排过队的会跳过(防止重复)。"""
        src = Path(src)
        dst = thumb_path_for(folder, src)
        with self._seen_lock:
            if src in self._seen:
                return dst
            self._seen.add(src)
        self._queue.put((src, dst))
        return dst

    def stop(self):
        """请求停止。worker 会在当前一张做完后退出。"""
        self._stop.set()
        # 放个哨兵唤醒阻塞的 get
        self._queue.put(None)

    def reset(self):
        """切换文件夹时调用:清空待处理队列和去重集合。

        注意:已经在 run() 循环内消费到的那一张不会被取消(要等它结束)。
        """
        # 清空队列(不阻塞)
        try:
            while True:
                self._queue.get_nowait()
        except queue.Empty:
            pass
        with self._seen_lock:
            self._seen.clear()

    # ---------- QThread 入口 ----------
    def run(self):
        def process(src: Path, dst: Path):
            try:
                if not dst.is_file():
                    make_thumbnail(src, dst)
                try:
                    from .exif_grouping import read_capture_time
                    t = read_capture_time(src) if not is_raw(src) else None
                except Exception:  # noqa: BLE001
                    t = None
                return src, dst, t, None
            except Exception as e:  # noqa: BLE001
                return src, dst, None, f"{type(e).__name__}: {e}"

        active = {}
        with ThreadPoolExecutor(max_workers=self._workers) as pool:
            while not self._stop.is_set():
                while len(active) < self._workers and not self._stop.is_set():
                    try:
                        item = self._queue.get_nowait()
                    except queue.Empty:
                        break
                    if item is None:
                        self._stop.set()
                        break
                    src, dst = item
                    active[pool.submit(process, src, dst)] = (src, dst)

                if not active:
                    try:
                        item = self._queue.get(timeout=0.3)
                    except queue.Empty:
                        self.idle.emit()
                        continue
                    if item is None:
                        break
                    src, dst = item
                    active[pool.submit(process, src, dst)] = (src, dst)
                    continue

                done, _ = wait(active, timeout=0.1, return_when=FIRST_COMPLETED)
                for fut in done:
                    active.pop(fut, None)
                    src, dst, capture_time, err = fut.result()
                    if err:
                        self.thumb_failed.emit(src, err)
                    else:
                        self.thumb_ready.emit(src, dst)
                        self.exif_time_ready.emit(src, capture_time)
