# -*- coding: utf-8 -*-
"""gui.utils 的纯函数测试。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gui.utils import cache_dir_for, fmt_duration, score_to_stars  # noqa: E402


class TestScoreToStars(unittest.TestCase):
    def test_zero_or_negative(self):
        self.assertEqual(score_to_stars(0), "")
        self.assertEqual(score_to_stars(-1), "")

    def test_buckets(self):
        # 1-2 → 1★
        self.assertEqual(score_to_stars(1), "★☆☆☆☆")
        self.assertEqual(score_to_stars(2), "★☆☆☆☆")
        # 3-4 → 2★
        self.assertEqual(score_to_stars(3), "★★☆☆☆")
        self.assertEqual(score_to_stars(4), "★★☆☆☆")
        # 5-6 → 3★
        self.assertEqual(score_to_stars(5), "★★★☆☆")
        self.assertEqual(score_to_stars(6), "★★★☆☆")
        # 7-8 → 4★
        self.assertEqual(score_to_stars(7), "★★★★☆")
        self.assertEqual(score_to_stars(8), "★★★★☆")
        # 9-10 → 5★
        self.assertEqual(score_to_stars(9), "★★★★★")
        self.assertEqual(score_to_stars(10), "★★★★★")

    def test_fractional(self):
        # 7.5 在 7-8 区间 → 4★
        self.assertEqual(score_to_stars(7.5), "★★★★☆")
        # 8.01 进入 9-10 区间 → 5★
        self.assertEqual(score_to_stars(8.01), "★★★★★")

    def test_string_input(self):
        self.assertEqual(score_to_stars("7"), "★★★★☆")
        self.assertEqual(score_to_stars(""), "")
        self.assertEqual(score_to_stars(None), "")


class TestFmtDuration(unittest.TestCase):
    def test_seconds(self):
        self.assertEqual(fmt_duration(5), "5s")
        self.assertEqual(fmt_duration(59.9), "60s")  # 四舍五入

    def test_minutes(self):
        self.assertEqual(fmt_duration(60), "1分00秒")
        self.assertEqual(fmt_duration(125), "2分05秒")
        self.assertEqual(fmt_duration(3599), "59分59秒")

    def test_hours(self):
        self.assertEqual(fmt_duration(3600), "1时00分")
        self.assertEqual(fmt_duration(3661), "1时01分")


class TestCacheDirFor(unittest.TestCase):
    def test_stable_hash(self):
        """同一路径应得到同一缓存目录。"""
        p = Path(r"C:\Photos\ShootA")
        self.assertEqual(cache_dir_for(p), cache_dir_for(p))

    def test_different_paths(self):
        a = cache_dir_for(Path(r"C:\Photos\ShootA"))
        b = cache_dir_for(Path(r"C:\Photos\ShootB"))
        self.assertNotEqual(a, b)

    def test_under_home(self):
        p = cache_dir_for(Path.cwd())
        self.assertTrue(str(p).startswith(str(Path.home())))


if __name__ == "__main__":
    unittest.main()
