# -*- coding: utf-8 -*-
"""run_batch 回调契约测试 — monkey-patch 掉模型调用,只验证流程/回调/CSV 写入。"""
import csv
import io
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import triage  # noqa: E402


def _make_fake_jpg(path: Path, size=(64, 48), color=(200, 150, 100)):
    """生成一个很小的假 JPG。"""
    img = Image.new("RGB", size, color=color)
    img.save(path, format="JPEG", quality=70)


def _fake_result(score: int = 7):
    """模拟 analyze_image 的返回。"""
    return {
        "content": {
            "scene_type": "portrait",
            "primary_subject": "测试主体",
            "impression": "测试感受",
            "shooting_intent": "posed",
            "has_person": True,
            "person_count": 1,
            "time_of_day": "afternoon",
            "dominant_colors": ["红色", "蓝色"],
        },
        "technical": {
            "sharpness": 4, "exposure": 3, "noise_level": 2,
            "white_balance": 4, "has_motion_blur": False,
            "is_motion_blur_intentional": None,
        },
        "aesthetic": {
            "composition": 7, "lighting": 7, "color": 7,
            "subject_clarity": 7, "storytelling": 6, "uniqueness": 5,
        },
        "portrait": {
            "expression": 7, "pose": 7, "eye_contact": 6, "flattering": 7,
            "portrait_note": "测试点评",
        },
        "overall": {
            "technical_score": 7, "aesthetic_score": 7, "overall_score": score,
            "strengths": ["具体优点 A", "具体优点 B"],
            "weaknesses": ["真问题 C"],
            "one_line_comment": "测试总评",
        },
    }


class TestRunBatch(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="triage_test_"))
        # 造 3 张假 JPG
        for i, score in enumerate([5, 7, 9], start=1):
            _make_fake_jpg(self.tmp / f"IMG_{i:03d}.jpg")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_progress_and_log_callbacks(self):
        """串行模式下,progress 和 log 都应被调用。"""
        progress_calls: list[tuple] = []
        log_calls: list[str] = []

        def fake_analyze(jpg, prompt=None, api_url=None):
            return _fake_result(7)

        with patch.object(triage, "analyze_image", fake_analyze):
            result = triage.run_batch(
                folder=self.tmp,
                concurrency=1,
                write_meta=False,   # 避免写 XMP 干扰测试
                on_progress=lambda jpg, row, done, total:
                    progress_calls.append((jpg.name, done, total)),
                on_log=lambda msg: log_calls.append(msg),
            )

        self.assertEqual(result["processed"], 3)
        self.assertEqual(result["failed"], 0)
        self.assertIsNone(result["fatal"])
        self.assertFalse(result["interrupted"])

        # 每张都触发一次 progress,total 恒为 3
        self.assertEqual(len(progress_calls), 3)
        for _, _, total in progress_calls:
            self.assertEqual(total, 3)
        # 最后一次 done 应为 3
        self.assertEqual(progress_calls[-1][1], 3)

        # 日志里至少有 "目录" / "待处理" / "写 XMP" 这些关键行
        joined = "\n".join(log_calls)
        self.assertIn("待处理", joined)

    def test_csv_written(self):
        """CSV 应包含所有字段且行数对齐。"""
        def fake_analyze(jpg, prompt=None, api_url=None):
            return _fake_result(7)

        with patch.object(triage, "analyze_image", fake_analyze):
            result = triage.run_batch(
                folder=self.tmp, concurrency=1, write_meta=False)

        csv_path = result["csv_path"]
        self.assertTrue(csv_path.is_file())

        with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            fieldnames = reader.fieldnames

        self.assertEqual(len(rows), 3)
        self.assertEqual(list(fieldnames), triage.CSV_FIELDS)
        # 人像字段应被正确填充
        for r in rows:
            self.assertEqual(r["场景"], "人像")
            self.assertEqual(r["拍摄意图"], "摆拍")
            self.assertEqual(r["神态"], "7")
            self.assertEqual(r["综合评分"], "7")
            # CSV 不应有换行(_clean 应该把它们清了)
            for v in r.values():
                self.assertNotIn("\n", v)
                self.assertNotIn("\r", v)

    def test_stop_flag(self):
        """stop_flag 返回 True 时应尽快退出。"""
        call_count = {"n": 0}

        def fake_analyze(jpg, prompt=None, api_url=None):
            call_count["n"] += 1
            return _fake_result(6)

        # 第一张完成后就停止
        stop_after_one = {"done": 0}

        def should_stop():
            return stop_after_one["done"] >= 1

        def on_progress(jpg, row, done, total):
            stop_after_one["done"] = done

        with patch.object(triage, "analyze_image", fake_analyze):
            result = triage.run_batch(
                folder=self.tmp, concurrency=1, write_meta=False,
                stop_flag=should_stop, on_progress=on_progress)

        # 应该处理了 1 张然后停,而不是 3 张
        self.assertLessEqual(result["processed"], 2)
        self.assertTrue(result["interrupted"])

    def test_fatal_from_runtime_error(self):
        """analyze_image 抛 RuntimeError 时视为致命错误,记录到 result.fatal。"""
        def bad_analyze(jpg, prompt=None, api_url=None):
            raise RuntimeError("llama-server 连接失败")

        with patch.object(triage, "analyze_image", bad_analyze):
            result = triage.run_batch(
                folder=self.tmp, concurrency=1, write_meta=False)

        self.assertIsNotNone(result["fatal"])
        self.assertIn("llama-server", result["fatal"])

    def test_skip_processed(self):
        """第二次跑同一目录应跳过已处理的照片。"""
        def fake_analyze(jpg, prompt=None, api_url=None):
            return _fake_result(7)

        with patch.object(triage, "analyze_image", fake_analyze):
            r1 = triage.run_batch(
                folder=self.tmp, concurrency=1, write_meta=False)
            self.assertEqual(r1["processed"], 3)

            r2 = triage.run_batch(
                folder=self.tmp, concurrency=1, write_meta=False)
            self.assertEqual(r2["processed"], 0)
            self.assertEqual(r2["skipped"], 3)

    def test_concurrency_parallel(self):
        """并发模式应跑完所有图,结果顺序可能不同但数量一致。"""
        def fake_analyze(jpg, prompt=None, api_url=None):
            return _fake_result(7)

        with patch.object(triage, "analyze_image", fake_analyze):
            result = triage.run_batch(
                folder=self.tmp, concurrency=4, write_meta=False)

        self.assertEqual(result["processed"], 3)
        self.assertEqual(result["failed"], 0)


if __name__ == "__main__":
    unittest.main()
