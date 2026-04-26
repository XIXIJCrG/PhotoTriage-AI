# -*- coding: utf-8 -*-
"""LR 导出 + StatsPanel 基础测试。"""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from PySide6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gui.lr_integration import write_picks_list  # noqa: E402
from gui.stats_panel import StatsPanel, _to_float  # noqa: E402


_app: QApplication | None = None


def _ensure_app():
    global _app
    if QApplication.instance() is None:
        _app = QApplication(sys.argv if sys.argv else ["t"])
    return QApplication.instance()


class TestLRPicksList(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="lr_test_"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_basic_list(self):
        out = self.tmp / "picks.txt"
        items = [
            (Path("A.jpg"), {"综合评分": "8", "一句话总评": "光影好"}),
            (Path("B.jpg"), {"综合评分": "3", "一句话总评": "废片"}),
        ]
        n = write_picks_list(items, out)
        self.assertEqual(n, 2)
        text = out.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(text), 2)
        self.assertTrue(text[0].startswith("A.jpg"))
        self.assertIn("4★", text[0])   # 8 分 → 4★
        self.assertIn("2★", text[1])   # 3 分 → 2★


class TestStatsPanel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _ensure_app()

    def test_to_float(self):
        self.assertEqual(_to_float("7"), 7.0)
        self.assertEqual(_to_float("7.5"), 7.5)
        self.assertEqual(_to_float("0"), 0.0)  # 0 是合法数字(即使模型很少返回)
        self.assertIsNone(_to_float(""))
        self.assertIsNone(_to_float("abc"))
        self.assertIsNone(_to_float(None))

    def test_update_empty(self):
        panel = StatsPanel()
        panel.update_stats([])
        # 不炸即可
        self.assertEqual(panel.card_total.value_label.text(), "0")

    def test_update_with_rows(self):
        panel = StatsPanel()
        rows = [
            {"综合评分": "8", "场景": "人像"},
            {"综合评分": "7", "场景": "人像"},
            {"综合评分": "4", "场景": "风光"},
            {"综合评分": "3", "场景": "风光"},
        ]
        panel.update_stats(rows)
        self.assertEqual(panel.card_total.value_label.text(), "4")
        # 平均 = (8+7+4+3)/4 = 5.5
        self.assertEqual(panel.card_avg.value_label.text(), "5.5")
        # pick = 2(8 和 7)
        self.assertTrue(panel.card_pick.value_label.text().startswith("2"))
        # waste = 2(4 和 3)
        self.assertTrue(panel.card_waste.value_label.text().startswith("2"))


if __name__ == "__main__":
    unittest.main()
