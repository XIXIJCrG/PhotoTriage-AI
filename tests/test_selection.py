# -*- coding: utf-8 -*-
"""同场分组选片测试。"""
from __future__ import annotations

import shutil
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from PIL import Image

from core.selection import apply_group_selection_to_rows, group_rows_for_selection


def _make_jpg(path: Path, capture: datetime | None = None):
    im = Image.new("RGB", (32, 24), color=(180, 180, 180))
    if capture is not None:
        exif = im.getexif()
        exif[0x9003] = capture.strftime("%Y:%m:%d %H:%M:%S")
        exif[0x0132] = capture.strftime("%Y:%m:%d %H:%M:%S")
        im.save(path, "JPEG", exif=exif.tobytes())
    else:
        im.save(path, "JPEG")


def _make_pattern_jpg(path: Path, shift: int = 0):
    im = Image.new("RGB", (64, 48), color=(245, 245, 235))
    px = im.load()
    for x in range(12 + shift, 42 + shift):
        for y in range(10, 32):
            px[x, y] = (40, 80, 180)
    for x in range(8 + shift, 58):
        for y in range(36, 40):
            px[x, y] = (30, 30, 30)
    im.save(path, "JPEG")


class TestSelectionGrouping(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="selection_test_"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_group_by_exif_time_and_rank(self):
        base = datetime(2026, 5, 11, 14, 0, 0)
        rows = []
        for name, delta, score in [
            ("A_001.jpg", 0, 7),
            ("A_002.jpg", 10, 9),
            ("A_003.jpg", 20, 5),
            ("B_001.jpg", 3600, 8),
        ]:
            _make_jpg(self.tmp / name, base + timedelta(seconds=delta))
            rows.append({"JPG文件名": name, "综合评分": score})

        apply_group_selection_to_rows(self.tmp, rows, gap_seconds=60)
        by_name = {row["JPG文件名"]: row for row in rows}

        self.assertEqual(by_name["A_002.jpg"]["分组ID"], "G0001")
        self.assertEqual(by_name["A_002.jpg"]["组内排名"], 1)
        self.assertEqual(by_name["A_002.jpg"]["组内推荐"], "精选")
        self.assertEqual(by_name["A_001.jpg"]["组内推荐"], "备选")
        self.assertEqual(by_name["A_003.jpg"]["组内推荐"], "淘汰")
        self.assertEqual(by_name["B_001.jpg"]["分组ID"], "G0002")
        self.assertEqual(by_name["B_001.jpg"]["组内推荐"], "单张")

    def test_group_by_filename_when_no_exif(self):
        rows = []
        for name, score in [("IMG_001.jpg", 6), ("IMG_002.jpg", 8), ("IMG_010.jpg", 9)]:
            _make_jpg(self.tmp / name, None)
            rows.append({"JPG文件名": name, "综合评分": score})

        groups = group_rows_for_selection(self.tmp, rows)

        self.assertEqual(len(groups), 2)
        self.assertEqual([item[0].name for item in groups[0]], ["IMG_001.jpg", "IMG_002.jpg"])
        self.assertEqual([item[0].name for item in groups[1]], ["IMG_010.jpg"])

    def test_group_by_visual_similarity_when_time_and_filename_are_unreliable(self):
        _make_pattern_jpg(self.tmp / "beach_pick.jpg", shift=0)
        _make_pattern_jpg(self.tmp / "random_name.jpg", shift=1)
        _make_jpg(self.tmp / "different_scene.jpg", None)
        rows = [
            {"JPG文件名": "beach_pick.jpg", "综合评分": 8},
            {"JPG文件名": "random_name.jpg", "综合评分": 9},
            {"JPG文件名": "different_scene.jpg", "综合评分": 7},
        ]

        groups = group_rows_for_selection(self.tmp, rows, use_visual_similarity=True)
        group_names = [[item[0].name for item in group] for group in groups]

        self.assertIn(["beach_pick.jpg", "random_name.jpg"], group_names)
        self.assertIn(["different_scene.jpg"], group_names)


if __name__ == "__main__":
    unittest.main()
