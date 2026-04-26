import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class TestI18nCatalogs(unittest.TestCase):
    def test_english_and_chinese_have_same_keys(self):
        zh = json.loads((ROOT / "i18n" / "zh-CN.json").read_text(encoding="utf-8"))
        en = json.loads((ROOT / "i18n" / "en-US.json").read_text(encoding="utf-8"))

        self.assertEqual(set(zh), set(en))


if __name__ == "__main__":
    unittest.main()
