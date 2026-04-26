# -*- coding: utf-8 -*-
"""批量操作:淘汰 / 撤销 / 导出 / 冲突处理。"""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gui.batch_actions import (  # noqa: E402
    DISCARD_SUBDIR,
    DiscardRecord,
    discard_files,
    export_files,
    undo_discard,
)


def _jpg(path: Path):
    Image.new("RGB", (64, 48), color=(100, 100, 200)).save(path, "JPEG")


def _raf(path: Path):
    path.write_bytes(b"FAKE_RAF_CONTENT")


def _xmp(path: Path, content: str = "<xmp/>"):
    path.write_text(content, encoding="utf-8")


class TestDiscardFiles(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp(prefix="discard_test_"))
        self.jpg_a = self.folder / "DSCF0001.JPG"
        self.raf_a = self.folder / "DSCF0001.RAF"
        self.xmp_a = self.folder / "DSCF0001.xmp"  # RAW 的 sidecar
        _jpg(self.jpg_a)
        _raf(self.raf_a)
        _xmp(self.xmp_a)

        self.jpg_b = self.folder / "DSCF0002.JPG"
        _jpg(self.jpg_b)
        # b 没 RAF / XMP

    def tearDown(self):
        shutil.rmtree(self.folder, ignore_errors=True)

    def _row(self, jpg_name: str, raw_name: str = ""):
        return {"JPG文件名": jpg_name, "RAW文件名": raw_name}

    def test_moves_jpg_raf_xmp(self):
        items = [(self.jpg_a, self._row("DSCF0001.JPG", "DSCF0001.RAF"))]
        record = discard_files(items, self.folder)

        discard_dir = self.folder / DISCARD_SUBDIR
        self.assertTrue((discard_dir / "DSCF0001.JPG").is_file())
        self.assertTrue((discard_dir / "DSCF0001.RAF").is_file())
        self.assertTrue((discard_dir / "DSCF0001.xmp").is_file())
        self.assertFalse(self.jpg_a.exists())
        self.assertFalse(self.raf_a.exists())
        self.assertFalse(self.xmp_a.exists())

        self.assertEqual(len(record.moves), 3)
        self.assertEqual(len(record.rows), 1)

    def test_moves_only_jpg_if_no_raf(self):
        items = [(self.jpg_b, self._row("DSCF0002.JPG"))]
        record = discard_files(items, self.folder)

        discard_dir = self.folder / DISCARD_SUBDIR
        self.assertTrue((discard_dir / "DSCF0002.JPG").is_file())
        self.assertEqual(len(record.moves), 1)

    def test_conflict_group_skip(self):
        """整组跳过:任一目标冲突就整组不动。"""
        discard_dir = self.folder / DISCARD_SUBDIR
        discard_dir.mkdir()
        (discard_dir / "DSCF0002.JPG").write_bytes(b"existing")

        items = [(self.jpg_b, self._row("DSCF0002.JPG"))]
        record = discard_files(items, self.folder)

        # jpg_b 仍在原位 → 未移动
        self.assertTrue(self.jpg_b.exists())
        self.assertEqual(len(record.moves), 0)
        # 整组跳过 → row 不进入 rows,而是记入 skipped
        self.assertEqual(len(record.rows), 0)
        self.assertEqual(len(record.skipped), 1)
        self.assertEqual(record.skipped[0], self.jpg_b)

    def test_conflict_on_raf_skips_whole_group(self):
        """RAF 冲突 → 整组(含 JPG)不动,避免孤儿。"""
        discard_dir = self.folder / DISCARD_SUBDIR
        discard_dir.mkdir()
        # JPG 目标没占,但 RAF 目标已占
        (discard_dir / "DSCF0001.RAF").write_bytes(b"existing")

        items = [(self.jpg_a, self._row("DSCF0001.JPG", "DSCF0001.RAF"))]
        record = discard_files(items, self.folder)

        # 关键:JPG 没被搬走,避免孤儿对
        self.assertTrue(self.jpg_a.is_file())
        self.assertTrue(self.raf_a.is_file())
        self.assertEqual(len(record.moves), 0)
        self.assertEqual(len(record.skipped), 1)


class TestUndoDiscard(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp(prefix="undo_test_"))
        self.jpg = self.folder / "DSCF0001.JPG"
        self.raf = self.folder / "DSCF0001.RAF"
        _jpg(self.jpg)
        _raf(self.raf)

    def tearDown(self):
        shutil.rmtree(self.folder, ignore_errors=True)

    def test_round_trip(self):
        items = [(self.jpg, {"JPG文件名": "DSCF0001.JPG",
                             "RAW文件名": "DSCF0001.RAF"})]
        record = discard_files(items, self.folder)

        self.assertFalse(self.jpg.exists())

        restored = undo_discard(record)
        self.assertEqual(restored, 2)  # JPG + RAF
        self.assertTrue(self.jpg.is_file())
        self.assertTrue(self.raf.is_file())

    def test_undo_skips_if_original_exists(self):
        """如果原位置又被填了(冲突),不覆盖。"""
        items = [(self.jpg, {"JPG文件名": "DSCF0001.JPG"})]
        record = discard_files(items, self.folder)

        # 假装原位置被别的东西占了
        self.jpg.write_bytes(b"SOMETHING_ELSE")

        restored = undo_discard(record)
        self.assertEqual(restored, 0)
        # _废片 里的文件没被动
        self.assertTrue((self.folder / DISCARD_SUBDIR / "DSCF0001.JPG").is_file())


class TestExportFiles(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp(prefix="export_src_"))
        self.dest = Path(tempfile.mkdtemp(prefix="export_dst_"))
        self.jpg = self.folder / "A.JPG"
        self.raf = self.folder / "A.RAF"
        _jpg(self.jpg)
        _raf(self.raf)

    def tearDown(self):
        shutil.rmtree(self.folder, ignore_errors=True)
        shutil.rmtree(self.dest, ignore_errors=True)

    def test_copies_jpg_and_raf(self):
        items = [(self.jpg, {"JPG文件名": "A.JPG", "RAW文件名": "A.RAF"})]
        jpg_n, raw_n = export_files(items, self.folder, self.dest)
        self.assertEqual(jpg_n, 1)
        self.assertEqual(raw_n, 1)
        self.assertTrue((self.dest / "A.JPG").is_file())
        self.assertTrue((self.dest / "A.RAF").is_file())
        # 原文件还在(copy 不是 move)
        self.assertTrue(self.jpg.is_file())

    def test_skip_raw_when_disabled(self):
        items = [(self.jpg, {"JPG文件名": "A.JPG", "RAW文件名": "A.RAF"})]
        jpg_n, raw_n = export_files(items, self.folder, self.dest,
                                    include_raw=False)
        self.assertEqual(jpg_n, 1)
        self.assertEqual(raw_n, 0)
        self.assertFalse((self.dest / "A.RAF").exists())

    def test_conflict_skipped(self):
        (self.dest / "A.JPG").write_bytes(b"existing")
        items = [(self.jpg, {"JPG文件名": "A.JPG"})]
        jpg_n, _ = export_files(items, self.folder, self.dest)
        self.assertEqual(jpg_n, 0)


if __name__ == "__main__":
    unittest.main()
