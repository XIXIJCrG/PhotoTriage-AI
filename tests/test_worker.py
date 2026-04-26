# -*- coding: utf-8 -*-
"""BatchWorker 信号桥接测试。"""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import triage  # noqa: E402
from gui.worker import BatchWorker  # noqa: E402


_app: QApplication | None = None


def _ensure_app():
    global _app
    if QApplication.instance() is None:
        _app = QApplication(sys.argv if sys.argv else ["test"])
    return QApplication.instance()


def _make_fake_jpg(path: Path):
    Image.new("RGB", (64, 48), color=(180, 100, 60)).save(
        path, format="JPEG", quality=70)


def _fake_result():
    return {
        "content": {
            "scene_type": "landscape", "primary_subject": "测试",
            "impression": "", "shooting_intent": "casual",
            "has_person": False, "person_count": 0,
            "time_of_day": "afternoon", "dominant_colors": [],
        },
        "technical": {
            "sharpness": 4, "exposure": 3, "noise_level": 2,
            "white_balance": 3, "has_motion_blur": False,
            "is_motion_blur_intentional": None,
        },
        "aesthetic": {
            "composition": 6, "lighting": 6, "color": 6,
            "subject_clarity": 6, "storytelling": 5, "uniqueness": 5,
        },
        "portrait": None,
        "overall": {
            "technical_score": 6, "aesthetic_score": 6, "overall_score": 6,
            "strengths": ["a", "b"], "weaknesses": [],
            "one_line_comment": "测试",
        },
    }


class TestBatchWorker(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _ensure_app()

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="worker_test_"))
        for i in range(2):
            _make_fake_jpg(self.tmp / f"IMG_{i:03d}.jpg")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_signals_fire(self):
        """progress / log / batch_done 都应触发一次以上。"""
        progress_events = []
        log_events = []
        done_events = []

        with patch.object(triage, "analyze_image",
                          lambda jpg, prompt=None, api_url=None: _fake_result()):
            worker = BatchWorker(folder=self.tmp, concurrency=1,
                                 write_meta=False)
            worker.progress.connect(
                lambda jpg, row, d, t: progress_events.append((jpg, d, t)))
            worker.log.connect(lambda msg: log_events.append(msg))

            loop = QEventLoop()
            worker.batch_done.connect(lambda r: done_events.append(r))
            worker.batch_done.connect(lambda r: loop.quit())
            worker.batch_failed.connect(lambda e: (done_events.append(("fail", e)),
                                                    loop.quit()))
            # 防御性超时:10 秒内必须完成
            QTimer.singleShot(10_000, loop.quit)

            worker.start()
            loop.exec()
            worker.wait(2000)

        self.assertEqual(len(progress_events), 2)
        self.assertGreater(len(log_events), 0)
        self.assertEqual(len(done_events), 1)
        result = done_events[0]
        self.assertEqual(result["processed"], 2)

    def test_stop_request(self):
        """request_stop 之后 worker 应尽快结束。"""
        with patch.object(triage, "analyze_image",
                          lambda jpg, prompt=None, api_url=None: _fake_result()):
            worker = BatchWorker(folder=self.tmp, concurrency=1,
                                 write_meta=False)

            loop = QEventLoop()
            worker.batch_done.connect(lambda r: loop.quit())
            QTimer.singleShot(5_000, loop.quit)

            worker.start()
            # 首次 progress 时请求停止
            worker.progress.connect(lambda *a: worker.request_stop())
            loop.exec()
            worker.wait(2000)

        self.assertTrue(worker.is_stop_requested())


if __name__ == "__main__":
    unittest.main()
