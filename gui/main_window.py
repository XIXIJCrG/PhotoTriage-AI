# -*- coding: utf-8 -*-
"""GUI 主窗口 — 完整功能版(P3 全量)。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from core.i18n import tr
from core.providers import LOCAL_PROVIDER, is_local_provider

from .history_sidebar import HistorySidebar
from .lr_integration import open_folder_in_lightroom
from .preview_window import PreviewWindow
from .progress_panel import ProgressPanel
from .prompt_editor import PromptEditorDialog
from .prompt_manager import DEFAULT_PROFILE_NAME, PromptStore
from .results_view import ResultsView
from .server_panel import ServerPanel
from .settings_dialog import SettingsDialog
from .stats_panel import StatsPanel
from .task_panel import TaskPanel
from .utils import app_settings
from .worker import BatchWorker


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(tr("app.name"))
        self.worker: BatchWorker | None = None
        self.preview: PreviewWindow | None = None
        self.prompt_store = PromptStore()
        self._restore_geometry()
        self._build_menu()
        self._build_ui()
        # 启动时如果上次 TaskPanel 记得某个文件夹,结果视图也加载
        if self.task_panel.folder:
            self.results_view.set_folder(self.task_panel.folder)
            self.history_sidebar.push_folder(self.task_panel.folder)
            self._refresh_stats()

    # ---------- UI ----------
    def _build_menu(self):
        mb = self.menuBar()

        m_file = mb.addMenu(tr("menu.file"))
        self.act_open = QAction(tr("menu.open_folder"), self)
        self.act_open.setShortcut(QKeySequence.Open)
        self.act_open.triggered.connect(self._menu_open_folder)
        m_file.addAction(self.act_open)
        m_file.addSeparator()
        act_quit = QAction(tr("menu.quit"), self)
        act_quit.setShortcut(QKeySequence.Quit)
        act_quit.triggered.connect(self.close)
        m_file.addAction(act_quit)

        m_view = mb.addMenu(tr("menu.view"))
        self.act_toggle_sidebar = QAction(tr("menu.show_sidebar"), self, checkable=True)
        saved_sidebar = bool(app_settings().value("ui/show_sidebar", True, type=bool))
        self.act_toggle_sidebar.setChecked(saved_sidebar)
        self.act_toggle_sidebar.toggled.connect(self._toggle_sidebar)
        m_view.addAction(self.act_toggle_sidebar)

        m_tools = mb.addMenu(tr("menu.tools"))
        act_prompt = QAction(tr("menu.prompt_editor"), self)
        act_prompt.triggered.connect(self._open_prompt_editor)
        m_tools.addAction(act_prompt)
        act_lr = QAction(tr("menu.open_in_lightroom"), self)
        act_lr.triggered.connect(self._open_in_lightroom)
        m_tools.addAction(act_lr)

        m_settings = mb.addMenu(tr("menu.settings"))
        act_settings = QAction(tr("menu.settings_action"), self)
        act_settings.triggered.connect(self._open_settings)
        m_settings.addAction(act_settings)
        m_settings.addSeparator()
        act_about = QAction(tr("menu.about"), self)
        act_about.triggered.connect(self._show_about)
        m_settings.addAction(act_about)

    def _build_ui(self):
        central = QWidget(self)
        self.setCentralWidget(central)

        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # 顶部:服务器
        self.server_panel = ServerPanel(self)
        self.server_panel.status_changed.connect(self._on_server_status)
        outer.addWidget(self.server_panel)
        outer.addWidget(_hline())

        # 任务
        self.task_panel = TaskPanel(prompt_store=self.prompt_store, parent=self)
        self.task_panel.start_requested.connect(self._on_start)
        self.task_panel.stop_requested.connect(self._on_stop)
        self.task_panel.folder_changed.connect(self._on_folder_changed)
        self.task_panel.edit_prompts_requested.connect(self._open_prompt_editor)
        outer.addWidget(self.task_panel)
        outer.addWidget(_hline())

        # 中部:侧栏 + tabs
        self.history_sidebar = HistorySidebar(self)
        self.history_sidebar.folder_selected.connect(self._on_history_folder)

        self.tabs = QTabWidget()
        self.progress_panel = ProgressPanel()
        self.results_view = ResultsView()
        self.results_view.preview_requested.connect(self._on_preview)
        self.stats_panel = StatsPanel()
        self.tabs.addTab(self.results_view, tr("tab.results"))
        self.tabs.addTab(self.stats_panel, tr("tab.stats"))
        self.tabs.addTab(self.progress_panel, tr("tab.progress"))
        self.tabs.setCurrentIndex(0)
        self.tabs.currentChanged.connect(self._on_tab_changed)

        split = QSplitter(Qt.Horizontal)
        split.addWidget(self.history_sidebar)
        split.addWidget(self.tabs)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setSizes([200, 1200])
        outer.addWidget(split, 1)

        # 应用视图菜单选项
        self.history_sidebar.setVisible(self.act_toggle_sidebar.isChecked())

        # 批处理期间 stats 刷新节流
        self._stats_refresh_timer = QTimer(self)
        self._stats_refresh_timer.setSingleShot(True)
        self._stats_refresh_timer.setInterval(2000)
        self._stats_refresh_timer.timeout.connect(self._refresh_stats)

        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage(tr("status.ready"))

    # ---------- 状态 ----------
    def _restore_geometry(self):
        s = app_settings()
        geom = s.value("window/geometry")
        if geom:
            self.restoreGeometry(geom)
        else:
            self.resize(1500, 950)

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            reply = QMessageBox.question(
                self, "退出确认",
                "批处理还在运行,是否停止并退出?",
                QMessageBox.Yes | QMessageBox.No)
            if reply != QMessageBox.Yes:
                event.ignore()
                return
            self.worker.request_stop()
            self.statusBar().showMessage("等待当前并发完成…")
            # 在 Qt 事件循环里等,给 UI 机会更新,不用 busy-loop 烧 CPU
            from PySide6.QtCore import QEventLoop, QTimer as _QT
            loop = QEventLoop()
            self.worker.finished.connect(loop.quit)
            _QT.singleShot(60_000, loop.quit)
            if self.worker.isRunning():
                loop.exec()
            if self.worker.isRunning():
                self.worker.terminate()
                self.worker.wait(2000)
        app_settings().setValue("window/geometry", self.saveGeometry())
        self.results_view.shutdown()
        self.server_panel.shutdown()
        if self.preview is not None:
            self.preview.close()
        super().closeEvent(event)

    # ---------- 服务器状态 ----------
    def _on_server_status(self, state: str):
        text = {
            "stopped": "服务器未启动",
            "starting": "服务器启动中…",
            "running": f"服务器运行中 — {self.server_panel.model_name or ''}",
            "dead": "服务器已停止",
        }.get(state, state)
        self.statusBar().showMessage(text)
        self.task_panel.set_server_ok(state == "running")

    # ---------- 文件夹切换 ----------
    def _on_folder_changed(self, folder: Path):
        self.results_view.set_folder(folder)
        self.history_sidebar.push_folder(folder)
        self._refresh_stats()

    def _on_history_folder(self, folder: Path):
        self.task_panel._set_folder(folder)

    def _menu_open_folder(self):
        self.task_panel._on_browse()

    def _toggle_sidebar(self, checked: bool):
        self.history_sidebar.setVisible(checked)
        app_settings().setValue("ui/show_sidebar", bool(checked))

    # ---------- Tabs ----------
    def _on_tab_changed(self, idx: int):
        if self.tabs.widget(idx) is self.stats_panel:
            self._refresh_stats()

    def _refresh_stats(self):
        items = self.results_view.current_visible_items()
        rows = [r for _, r in items]
        self.stats_panel.update_stats(rows)

    # ---------- 任务启停 ----------
    def _on_start(self, folder: Path, concurrency: int,
                  write_meta: bool, profile_name: str):
        if self.worker and self.worker.isRunning():
            return
        self.results_view.set_folder(folder)
        profile = self.prompt_store.get(profile_name)
        prompt_text = profile.prompt if profile else None
        label = "" if profile_name == DEFAULT_PROFILE_NAME else profile_name

        self.progress_panel.reset()
        self.progress_panel.append_log(f"▶ 开始分析: {folder}")
        metadata_mode = app_settings().value("task/metadata_mode", "embed") or "embed"
        meta_desc = "否" if not write_meta else ("只写 sidecar" if metadata_mode == "sidecar" else "嵌入 JPG/PNG")
        self.progress_panel.append_log(
            f"  并发 {concurrency} · 写元数据 {meta_desc} · "
            f"Prompt: {profile_name}")
        self.progress_panel.start(0)

        self.tabs.setCurrentWidget(self.progress_panel)

        provider_type = app_settings().value("provider/type", LOCAL_PROVIDER) or LOCAL_PROVIDER
        if not is_local_provider(provider_type):
            accepted = bool(app_settings().value(
                "provider/cloud_warning_accepted", False, type=bool))
            if not accepted:
                answer = QMessageBox.warning(
                    self,
                    tr("cloud.warning.title"),
                    tr("cloud.warning.body"),
                    QMessageBox.Ok | QMessageBox.Cancel,
                    QMessageBox.Cancel,
                )
                if answer != QMessageBox.Ok:
                    return
                app_settings().setValue("provider/cloud_warning_accepted", True)
        base_url = app_settings().value("provider/base_url", "") or ""
        model = app_settings().value("provider/model", "") or ""
        api_key = app_settings().value("provider/api_key", "") or ""
        api_url = app_settings().value("server/api_url", None) or None
        self.worker = BatchWorker(
            folder=folder, concurrency=concurrency,
            write_meta=write_meta, metadata_mode=metadata_mode, prompt=prompt_text,
            prompt_label=label, api_url=api_url, base_url=base_url, model=model,
            api_key=api_key, provider_type=provider_type, parent=self,
        )
        self.worker.progress.connect(self._on_worker_progress)
        self.worker.log.connect(self.progress_panel.append_log)
        self.worker.batch_done.connect(self._on_worker_done)
        self.worker.batch_failed.connect(self._on_worker_failed)
        self.worker.finished.connect(self._on_worker_finished)

        self.task_panel.set_running(True)
        self.results_view.set_batch_running(True)
        self.statusBar().showMessage("分析中…")
        self.worker.start()

    def _on_stop(self):
        if self.worker and self.worker.isRunning():
            self.worker.request_stop()

    def _on_worker_progress(self, jpg: Path, row: dict, done: int, total: int):
        self.progress_panel.on_progress(jpg, row, done, total)
        if not row.get("错误"):
            self.results_view.append_row(jpg, row)
        # 若当前在 stats tab,节流刷新一下(2s 窗口合并)
        if self.tabs.currentWidget() is self.stats_panel:
            if not self._stats_refresh_timer.isActive():
                self._stats_refresh_timer.start()

    def _on_worker_done(self, result: dict):
        self.progress_panel.on_done(result)
        fatal = result.get("fatal")
        if fatal:
            self.statusBar().showMessage(f"异常终止: {fatal}")
        elif result.get("interrupted"):
            self.statusBar().showMessage("已停止")
        else:
            processed = result.get("processed", 0)
            self.statusBar().showMessage(f"完成 · 新处理 {processed} 张")
        if not fatal:
            self.tabs.setCurrentWidget(self.results_view)
        self._refresh_stats()

    def _on_worker_failed(self, err: str):
        self.task_panel.set_running(False)
        self.results_view.set_batch_running(False)
        self.progress_panel.append_log(f"\n✗ 批处理异常: {err}")
        self.statusBar().showMessage(f"批处理异常: {err}")
        QTimer.singleShot(0, lambda: QMessageBox.critical(self, "批处理异常", err))

    def _on_worker_finished(self):
        self.task_panel.set_running(False)
        self.results_view.set_batch_running(False)
        if self.worker is not None:
            self.worker.deleteLater()
            self.worker = None

    # ---------- 预览 ----------
    def _on_preview(self, jpg: Path, row: dict):
        if self.preview is None:
            self.preview = PreviewWindow(self)
        items = self.results_view.current_visible_items()
        try:
            idx = next(i for i, (p, _) in enumerate(items)
                       if p.name == jpg.name)
        except StopIteration:
            idx = 0
            items = [(jpg, row)]
        self.preview.show_list(items, idx)
        self.preview.show()
        self.preview.raise_()
        self.preview.activateWindow()

    # ---------- 菜单动作 ----------
    def _open_settings(self):
        dlg = SettingsDialog(self)
        dlg.exec()

    def _open_prompt_editor(self):
        dlg = PromptEditorDialog(self.prompt_store, self)
        dlg.exec()
        # 编辑完刷新任务面板的下拉
        self.task_panel.reload_prompt_profiles()

    def _open_in_lightroom(self):
        folder = self.results_view.folder or self.task_panel.folder
        if folder is None:
            QMessageBox.warning(self, "未选择目录", "请先选择一个照片目录。")
            return
        ok, msg = open_folder_in_lightroom(folder)
        if not ok:
            QMessageBox.warning(self, "Lightroom", msg)
        else:
            self.statusBar().showMessage(msg)

    def _show_about(self):
        QMessageBox.about(
            self, tr("about.title"),
            "<h3>照片筛选工具</h3>"
            "<p>OpenAI-compatible 视觉模型驱动的批量初筛 + 可视化选片。</p>"
            "<p>UI:PySide6</p>"
            "<p>XMP 元数据写入兼容 Lightroom / Capture One / Bridge。</p>"
        )


def _hline() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.HLine)
    f.setFrameShadow(QFrame.Sunken)
    return f
