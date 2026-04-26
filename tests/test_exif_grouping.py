# -*- coding: utf-8 -*-
"""EXIF 时间聚类测试。"""
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gui.exif_grouping import group_by_time, read_capture_time  # noqa: E402


def _make_jpg(path: Path, capture: datetime | None = None):
    im = Image.new("RGB", (32, 24), color=(200, 200, 200))
    if capture is not None:
        # 写 EXIF DateTimeOriginal
        exif = im.getexif()
        exif[0x9003] = capture.strftime("%Y:%m:%d %H:%M:%S")
        exif[0x0132] = capture.strftime("%Y:%m:%d %H:%M:%S")
        im.save(path, "JPEG", exif=exif.tobytes())
    else:
        im.save(path, "JPEG")


class TestReadCaptureTime(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="exif_test_"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_with_exif(self):
        p = self.tmp / "a.jpg"
        when = datetime(2026, 4, 24, 15, 30, 0)
        _make_jpg(p, when)
        got = read_capture_time(p)
        self.assertEqual(got, when)

    def test_without_exif(self):
        p = self.tmp / "noexif.jpg"
        _make_jpg(p, None)
        self.assertIsNone(read_capture_time(p))


class TestGroupByTime(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="group_test_"))
        base = datetime(2026, 4, 24, 15, 0, 0)
        self.items = []
        # 3 张同场(15:00:00, 15:00:10, 15:00:30)
        for i, dt in enumerate([0, 10, 30]):
            p = self.tmp / f"A_{i}.jpg"
            _make_jpg(p, base + timedelta(seconds=dt))
            self.items.append((p, {"JPG文件名": p.name}))
        # 3 张下一场(16:00:00, 16:00:05, 16:00:20)
        base2 = datetime(2026, 4, 24, 16, 0, 0)
        for i, dt in enumerate([0, 5, 20]):
            p = self.tmp / f"B_{i}.jpg"
            _make_jpg(p, base2 + timedelta(seconds=dt))
            self.items.append((p, {"JPG文件名": p.name}))
        # 1 张没 EXIF
        p_noexif = self.tmp / "X.jpg"
        _make_jpg(p_noexif, None)
        self.items.append((p_noexif, {"JPG文件名": p_noexif.name}))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_two_groups_plus_noexif(self):
        groups = group_by_time(self.items, gap_seconds=60)
        # 应得到 3 组:场 A / 场 B / 无时间
        self.assertEqual(len(groups), 3)
        self.assertEqual(len(groups[0]), 3)
        self.assertEqual(len(groups[1]), 3)
        self.assertEqual(len(groups[2]), 1)  # 无时间那张
        self.assertEqual(groups[2][0][0].name, "X.jpg")


if __name__ == "__main__":
    unittest.main()
