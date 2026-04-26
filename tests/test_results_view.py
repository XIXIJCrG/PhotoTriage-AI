# -*- coding: utf-8 -*-
"""ResultsView + PhotoFilterProxy 测试。"""
import csv
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gui.photo_card_delegate import ROLE_JPG_PATH, ROLE_ROW  # noqa: E402
from gui.results_view import PhotoFilterProxy, ResultsView  # noqa: E402
from gui.utils import cache_dir_for  # noqa: E402
from triage import CSV_FIELDS  # noqa: E402


_app: QApplication | None = None


def _ensure_app():
    global _app
    if QApplication.instance() is None:
        _app = QApplication(sys.argv if sys.argv else ["test"])
    return QApplication.instance()


def _make_jpg(path: Path, size=(200, 150)):
    Image.new("RGB", size, color=(100, 200, 150)).save(
        path, "JPEG", quality=80)


def _make_row(jpg_name: str, score: int, scene: str = "人像",
              has_person: str = "是"):
    row = {f: "" for f in CSV_FIELDS}
    row.update({
        "JPG文件名": jpg_name,
        "场景": scene,
        "拍摄意图": "摆拍",
        "主体": f"测试 {jpg_name}",
        "有人": has_person,
        "综合评分": str(score),
        "艺术总分": str(score),
        "技术总分": str(score),
    })
    return row


def _write_csv(folder: Path, rows: list[dict]) -> Path:
    p = folder / "triage_test.csv"
    with p.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    return p


class TestPhotoFilterProxy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _ensure_app()

    def _make_model(self, rows: list[dict]) -> QStandardItemModel:
        model = QStandardItemModel()
        for r in rows:
            item = QStandardItem()
            item.setData(r.get("JPG文件名", ""), ROLE_JPG_PATH)
            item.setData(r, ROLE_ROW)
            model.appendRow(item)
        return model

    def test_filter_score_range(self):
        model = self._make_model([
            _make_row("a.jpg", 4),
            _make_row("b.jpg", 6),
            _make_row("c.jpg", 8),
        ])
        proxy = PhotoFilterProxy()
        proxy.setSourceModel(model)
        proxy.set_filters(6, 10, "", "")
        self.assertEqual(proxy.rowCount(), 2)

    def test_filter_scene(self):
        model = self._make_model([
            _make_row("a.jpg", 7, scene="人像"),
            _make_row("b.jpg", 7, scene="风光"),
            _make_row("c.jpg", 7, scene="街拍"),
        ])
        proxy = PhotoFilterProxy()
        proxy.setSourceModel(model)
        proxy.set_filters(0, 10, "风光", "")
        self.assertEqual(proxy.rowCount(), 1)

    def test_sort_by_score_desc(self):
        model = self._make_model([
            _make_row("low.jpg", 3),
            _make_row("high.jpg", 9),
            _make_row("mid.jpg", 6),
        ])
        proxy = PhotoFilterProxy()
        proxy.setSourceModel(model)
        proxy.set_sort("综合评分", ascending=False)
        # 检查前三顺序
        names = []
        for r in range(proxy.rowCount()):
            src = proxy.mapToSource(proxy.index(r, 0))
            names.append(model.itemFromIndex(src).data(ROLE_JPG_PATH))
        self.assertEqual(names, ["high.jpg", "mid.jpg", "low.jpg"])

    def test_sort_by_score_asc(self):
        model = self._make_model([
            _make_row("a.jpg", 9),
            _make_row("b.jpg", 3),
            _make_row("c.jpg", 6),
        ])
        proxy = PhotoFilterProxy()
        proxy.setSourceModel(model)
        proxy.set_sort("综合评分", ascending=True)
        names = []
        for r in range(proxy.rowCount()):
            src = proxy.mapToSource(proxy.index(r, 0))
            names.append(model.itemFromIndex(src).data(ROLE_JPG_PATH))
        self.assertEqual(names, ["b.jpg", "c.jpg", "a.jpg"])


class TestResultsViewLoadCsv(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _ensure_app()

    def setUp(self):
        self.folder = Path(tempfile.mkdtemp(prefix="results_test_"))
        # 生成假 JPG
        for name in ("A.jpg", "B.jpg", "C.jpg"):
            _make_jpg(self.folder / name)
        # 写 CSV
        _write_csv(self.folder, [
            _make_row("A.jpg", 4, scene="人像"),
            _make_row("B.jpg", 7, scene="风光"),
            _make_row("C.jpg", 9, scene="人像"),
        ])

    def tearDown(self):
        cache = cache_dir_for(self.folder)
        shutil.rmtree(cache, ignore_errors=True)
        view = getattr(self, "view", None)
        if view is not None:
            view.shutdown()
        shutil.rmtree(self.folder, ignore_errors=True)

    def test_load_all_rows(self):
        view = ResultsView()
        self.view = view
        view.set_folder(self.folder)

        self.assertEqual(view.model.rowCount(), 3)
        self.assertEqual(view.proxy.rowCount(), 3)  # 默认不筛选

    def test_filter_then_visible(self):
        view = ResultsView()
        self.view = view
        view.set_folder(self.folder)

        # 设置筛选:综合分 >=7
        view.filter_bar.min_spin.setValue(7)
        QApplication.processEvents()

        self.assertEqual(view.proxy.rowCount(), 2)

        visible = view.current_visible_items()
        self.assertEqual(len(visible), 2)
        # 第一项应该是 9 分的 C.jpg(默认降序)
        self.assertEqual(visible[0][0].name, "C.jpg")

    def test_append_row_live(self):
        view = ResultsView()
        self.view = view
        view.set_folder(self.folder)

        count_before = view.model.rowCount()
        jpg = self.folder / "A.jpg"  # 已存在的,应做更新
        new_row = _make_row("A.jpg", 10, scene="人像")
        view.append_row(jpg, new_row)
        self.assertEqual(view.model.rowCount(), count_before)  # 不增加

        # 新增一个不在 CSV 的
        jpg_new = self.folder / "D.jpg"
        _make_jpg(jpg_new)
        view.append_row(jpg_new, _make_row("D.jpg", 8))
        self.assertEqual(view.model.rowCount(), count_before + 1)


if __name__ == "__main__":
    unittest.main()
