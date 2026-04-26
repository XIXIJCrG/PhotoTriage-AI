# -*- coding: utf-8 -*-
"""PromptStore 测试。"""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gui.prompt_manager import DEFAULT_PROFILE_NAME, PromptStore  # noqa: E402


class TestPromptStore(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="prompt_test_"))
        self.path = self.tmp / "prompts.json"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_default_always_present(self):
        s = PromptStore(path=self.path)
        self.assertIn(DEFAULT_PROFILE_NAME, s.list_names())
        self.assertEqual(s.list_names()[0], DEFAULT_PROFILE_NAME)

    def test_default_cannot_delete(self):
        s = PromptStore(path=self.path)
        self.assertFalse(s.delete(DEFAULT_PROFILE_NAME))
        self.assertIn(DEFAULT_PROFILE_NAME, s.list_names())

    def test_upsert_and_persist(self):
        s = PromptStore(path=self.path)
        s.upsert("严苛版", "你是极严苛的评审…")
        self.assertTrue(self.path.is_file())

        # 重新加载
        s2 = PromptStore(path=self.path)
        p = s2.get("严苛版")
        self.assertIsNotNone(p)
        self.assertEqual(p.prompt, "你是极严苛的评审…")

    def test_list_order(self):
        s = PromptStore(path=self.path)
        s.upsert("z-晚", "x")
        s.upsert("a-早", "y")
        names = s.list_names()
        self.assertEqual(names[0], DEFAULT_PROFILE_NAME)
        # 非默认按字母序
        self.assertEqual(names[1:], sorted(names[1:]))

    def test_delete(self):
        s = PromptStore(path=self.path)
        s.upsert("临时", "x")
        self.assertTrue(s.delete("临时"))
        self.assertIsNone(s.get("临时"))
        self.assertFalse(s.delete("不存在"))


if __name__ == "__main__":
    unittest.main()
