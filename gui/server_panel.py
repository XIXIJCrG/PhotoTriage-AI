# -*- coding: utf-8 -*-
"""llama-server 启动/停止/状态面板。"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.providers import LOCAL_PROVIDER, is_local_provider

from triage import API_URL, DEFAULT_BASE_URL, DEFAULT_MODEL, check_server

from .utils import app_settings


# Windows 下启动新控制台窗口的标志
CREATE_NEW_CONSOLE = 0x00000010 if sys.platform == "win32" else 0


class StatusLight(QWidget):
    """一个小圆点状态灯。"""

    COLORS = {
        "stopped": QColor("#9E9E9E"),   # 灰
        "starting": QColor("#FFB300"),  # 黄
        "running": QColor("#43A047"),   # 绿
        "dead": QColor("#E53935"),      # 红
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self._state = "stopped"
        self.setFixedSize(14, 14)

    def set_state(self, state: str):
        if state != self._state:
            self._state = state
            self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(self.COLORS.get(self._state, self.COLORS["stopped"]))
        p.setPen(Qt.NoPen)
        p.drawEllipse(1, 1, 12, 12)


class PingWorker(QThread):
    """后台 ping llama-server,避免阻塞 UI。"""

    result_ready = Signal(bool, str)

    def __init__(
        self,
        api_url: str,
        base_url: str,
        api_key: str,
        model: str,
        parent=None,
    ):
        super().__init__(parent)
        self.api_url = api_url
        self.base_url = base_url
        self.api_key = api_key
        self.model = model

    def run(self):
        ok, info = check_server(
            self.api_url,
            timeout=3,
            base_url=self.base_url,
            api_key=self.api_key,
            model=self.model,
        )
        self.result_ready.emit(ok, info)


class ServerPanel(QWidget):
    """服务器状态控制面板。"""

    status_changed = Signal(str)  # 发出最新状态字符串:stopped/starting/running/dead

    def __init__(self, parent=None):
        super().__init__(parent)
        self.proc: Optional[subprocess.Popen] = None
        self.state: str = "stopped"
        self.model_name: str = ""
        self._pending_ping: Optional[PingWorker] = None

        self._build_ui()

        # 定时轮询状态
        self.timer = QTimer(self)
        self.timer.setInterval(2500)
        self.timer.timeout.connect(self.refresh_status)
        self.timer.start()
        self.refresh_status()

    # ---------- UI ----------

    def _build_ui(self):
        self.light = StatusLight()
        self.status_label = QLabel("未启动")
        self.status_label.setMinimumWidth(80)

        self.model_label = QLabel("")
        self.model_label.setStyleSheet("color: #666;")
        self.model_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.model_label.setMinimumWidth(120)
        # 防止长错误信息撑大窗口:超出省略
        self.model_label.setTextInteractionFlags(Qt.TextSelectableByMouse)

        self.start_btn = QPushButton("启动服务")
        self.stop_btn = QPushButton("停止服务")
        self.stop_btn.setEnabled(False)

        self.script_btn = QPushButton("…")
        self.script_btn.setToolTip("选择 start-triage-server.bat 路径")
        self.script_btn.setFixedWidth(32)

        self.start_btn.clicked.connect(self._on_start)
        self.stop_btn.clicked.connect(self._on_stop)
        self.script_btn.clicked.connect(self._on_pick_script)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.addWidget(self.light)
        lay.addWidget(self.status_label)
        lay.addSpacing(8)
        lay.addWidget(self.model_label, 1)
        lay.addSpacing(8)
        lay.addWidget(self.start_btn)
        lay.addWidget(self.stop_btn)
        lay.addWidget(self.script_btn)

    # ---------- 脚本路径 ----------

    def _script_path(self) -> Optional[Path]:
        s = app_settings().value("server/script_path", "")
        if s and Path(s).is_file():
            return Path(s)
        # 默认同目录下的 start-triage-server.bat
        default = Path(__file__).resolve().parent.parent / "start-triage-server.bat"
        if default.is_file():
            return default
        return None

    def _on_pick_script(self):
        current = self._script_path()
        start_dir = str(current.parent) if current else ""
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 llama-server 启动脚本", start_dir,
            "批处理脚本 (*.bat *.cmd);;所有文件 (*.*)",
        )
        if path:
            app_settings().setValue("server/script_path", path)
            QMessageBox.information(self, "已保存",
                                    f"启动脚本已设置为:\n{path}")

    # ---------- 启/停 ----------

    def _on_start(self):
        if not is_local_provider(app_settings().value("provider/type", LOCAL_PROVIDER)):
            QMessageBox.information(self, "Cloud API", "当前使用云端 API,无需启动本地服务。")
            return
        if self.proc and self.proc.poll() is None:
            return
        script = self._script_path()
        if not script:
            QMessageBox.warning(
                self, "未找到启动脚本",
                "请先通过右侧 … 按钮选择 start-triage-server.bat 的路径。")
            return
        try:
            self.proc = subprocess.Popen(
                [str(script)],
                cwd=str(script.parent),
                creationflags=CREATE_NEW_CONSOLE,
                shell=False,
            )
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "启动失败", str(e))
            return
        self._set_state("starting")
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)

    def _on_stop(self):
        if self.proc and self.proc.poll() is None:
            # Windows 下用 taskkill 杀进程树(包括 cmd + llama-server.exe)
            if sys.platform == "win32":
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(self.proc.pid)],
                    capture_output=True, check=False,
                )
            else:
                self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None
        self._set_state("stopped")
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

    def shutdown(self):
        """由主窗口关闭时调用:停掉定时器、等完 ping、kill 服务。"""
        self.timer.stop()
        if self._pending_ping is not None:
            try:
                self._pending_ping.result_ready.disconnect()
            except Exception:
                pass
            self._pending_ping.wait(3000)
            self._pending_ping = None
        if self.proc and self.proc.poll() is None:
            self._on_stop()

    # ---------- 状态机 ----------

    def _set_state(self, state: str):
        if state == self.state:
            return
        self.state = state
        self.light.set_state(state)
        text_map = {
            "stopped": "未启动",
            "starting": "启动中…",
            "running": "运行中",
            "dead": "已停止",
        }
        self.status_label.setText(text_map.get(state, state))
        self.status_changed.emit(state)

    def refresh_status(self):
        """每 2.5 秒被定时器调用;也在启停操作后显式调用一次。"""
        # 进程先看本地状态
        has_proc = self.proc is not None and self.proc.poll() is None
        if self.state == "running" and not has_proc and self.proc is not None:
            # 我们启动的进程被外部关了
            self.proc = None
            self._set_state("dead")
            self.start_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            self.stop_btn.setToolTip("")

        # 不管有没有 proc,都尝试 ping(可能服务器是手动启动的)
        if self._pending_ping is not None:
            return  # 上一次还没回来,不发新的

        provider_type = app_settings().value("provider/type", LOCAL_PROVIDER) or LOCAL_PROVIDER
        base_url = app_settings().value("provider/base_url", DEFAULT_BASE_URL) or DEFAULT_BASE_URL
        model = app_settings().value("provider/model", DEFAULT_MODEL) or DEFAULT_MODEL
        api_key = app_settings().value("provider/api_key", "") or ""
        api_url = app_settings().value("server/api_url", API_URL) or API_URL
        if not is_local_provider(provider_type):
            self.start_btn.setEnabled(False)
            self.start_btn.setToolTip("当前使用云端 API,无需启动本地服务")
            self.stop_btn.setEnabled(False)
        elif self.proc is None and self.state != "running":
            self.start_btn.setEnabled(True)
            self.start_btn.setToolTip("")
        w = PingWorker(api_url, base_url, api_key, model, self)
        w.result_ready.connect(self._on_ping_done)
        w.finished.connect(lambda: self._clear_pending(w))
        self._pending_ping = w
        w.start()

    def _clear_pending(self, w: PingWorker):
        if self._pending_ping is w:
            self._pending_ping = None

    def _on_ping_done(self, ok: bool, info: str):
        if ok:
            self.model_name = info
            msg = info if len(info) <= 60 else info[:57] + "…"
            self.model_label.setText(f"模型: {msg}")
            self.model_label.setToolTip(f"模型: {info}")
            if self.state != "running":
                self._set_state("running")
            # 按钮状态跟随是否有自己启动的进程
            if self.proc is None:
                # 外部启动的服务
                self.start_btn.setEnabled(False)
                self.start_btn.setToolTip("服务器已在外部运行")
                self.stop_btn.setEnabled(False)
                self.stop_btn.setToolTip("服务器由外部启动,无法从此处停止")
            else:
                self.start_btn.setEnabled(False)
                self.start_btn.setToolTip("")
                self.stop_btn.setEnabled(True)
                self.stop_btn.setToolTip("")
        else:
            # 错误信息可能很长,截断避免撑大窗口
            msg = info if len(info) <= 60 else info[:57] + "…"
            self.model_label.setText(f"ping 失败: {msg}")
            self.model_label.setToolTip(f"ping 失败: {info}")
            if self.state == "running":
                # 服务器从 running 变不可达
                if self.proc is not None and self.proc.poll() is None:
                    # 进程还在,可能是短暂故障,保持状态等下一轮
                    return
                self._set_state("dead")
                self.start_btn.setEnabled(True)
                self.stop_btn.setEnabled(False)
