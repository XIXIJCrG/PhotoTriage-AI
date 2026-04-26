# -*- coding: utf-8 -*-
"""缩略图生成器测试。"""
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gui.thumbnail_gen import (  # noqa: E402
    THUMB_SIZE,
    ThumbnailGenerator,
    make_thumbnail,
    thumb_path_for,
)
from gui.utils import cache_dir_for  # noqa: E402


_app: QApplication | None = None


def _ensure_app():
    global _app
    if QApplication.instance() is None:
        _app = QApplication(sys.argv if sys.argv else ["test"])
    return QApplication.instance()


def _make_jpg(path: Path, size=(800, 600)):
    Image.new("RGB", size, color=(120, 180, 200)).save(
        path, "JPEG", quality=85)


class TestMakeThumbnail(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="thumb_test_"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_landscape(self):
        src = self.tmp / "wide.jpg"
        dst = self.tmp / "out.jpg"
        _make_jpg(src, (800, 600))
        make_thumbnail(src, dst)
        self.assertTrue(dst.is_file())
        with Image.open(dst) as im:
            self.assertLessEqual(max(im.size), THUMB_SIZE)

    def test_portrait(self):
        src = self.tmp / "tall.jpg"
        dst = self.tmp / "out.jpg"
        _make_jpg(src, (400, 800))
        make_thumbnail(src, dst)
        with Image.open(dst) as im:
            self.assertLessEqual(max(im.size), THUMB_SIZE)

    def test_already_small(self):
        src = self.tmp / "small.jpg"
        dst = self.tmp / "out.jpg"
        _make_jpg(src, (100, 80))
        make_thumbnail(src, dst)
        with Image.open(dst) as im:
            # 不会放大
            self.assertLessEqual(max(im.size), 100)


class TestThumbPathFor(unittest.TestCase):
    def test_stem_only(self):
        folder = Path.home() / "dummy_folder"
        p = thumb_path_for(folder, Path("DSCF1234.JPG"))
        self.assertTrue(p.name.startswith("DSCF1234-"))
        self.assertEqual(p.suffix, ".jpg")
        self.assertTrue(str(p).startswith(str(Path.home())))

    def test_same_stem_different_ext_no_longer_collides(self):
        """同名不同扩展的照片不应误用同一张缩略图缓存。"""
        folder = Path.home() / "dummy_folder"
        a = thumb_path_for(folder, Path("IMG_1.jpg"))
        b = thumb_path_for(folder, Path("IMG_1.png"))
        self.assertNotEqual(a, b)


class TestThumbnailGenerator(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _ensure_app()

    def setUp(self):
        self.folder = Path(tempfile.mkdtemp(prefix="thumbgen_test_"))
        self.photos = []
        for i in range(3):
            p = self.folder / f"IMG_{i:03d}.jpg"
            _make_jpg(p, (800, 600))
            self.photos.append(p)

    def tearDown(self):
        # 把生成的缓存一起清掉
        cache = cache_dir_for(self.folder)
        shutil.rmtree(cache, ignore_errors=True)
        shutil.rmtree(self.folder, ignore_errors=True)

    def test_end_to_end(self):
        gen = ThumbnailGenerator()
        ready_events = []
        gen.thumb_ready.connect(
            lambda src, dst: ready_events.append((Path(src), Path(dst))))
        gen.start()
        try:
            for p in self.photos:
                gen.enqueue(p, self.folder)

            # 等 5 秒或收到 3 个 ready
            loop = QEventLoop()
            checker = QTimer()
            checker.setInterval(100)
            def check():
                if len(ready_events) >= 3:
                    loop.quit()
            checker.timeout.connect(check)
            checker.start()
            QTimer.singleShot(5000, loop.quit)
            loop.exec()
        finally:
            gen.stop()
            gen.wait(2000)

        self.assertEqual(len(ready_events), 3)
        for src, dst in ready_events:
            self.assertTrue(dst.is_file())
            with Image.open(dst) as im:
                self.assertLessEqual(max(im.size), THUMB_SIZE)

    def test_dedup(self):
        """enqueue 同一张图两次应该只处理一次。"""
        gen = ThumbnailGenerator()
        events = []
        gen.thumb_ready.connect(
            lambda src, dst: events.append(Path(src)))
        gen.start()
        try:
            p = self.photos[0]
            gen.enqueue(p, self.folder)
            gen.enqueue(p, self.folder)
            gen.enqueue(p, self.folder)

            loop = QEventLoop()
            QTimer.singleShot(2000, loop.quit)
            loop.exec()
        finally:
            gen.stop()
            gen.wait(2000)

        self.assertEqual(len(events), 1)


if __name__ == "__main__":
    unittest.main()
