# -*- coding: utf-8 -*-
"""结果视图:筛选栏 + 缩略图网格 + 缩略图生成器。"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Optional

from PySide6.QtCore import (
    QModelIndex,
    QSize,
    QSortFilterProxyModel,
    QTimer,
    Qt,
    Signal,
)
from PySide6.QtGui import QKeySequence, QPixmap, QShortcut, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QListView,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from triage import scan_folder

from .batch_actions import (
    BatchActionsBar,
    DISCARD_SUBDIR,
    DiscardRecord,
    discard_files,
    export_files,
    undo_discard,
)
from .compare_window import CompareWindow
from .exif_grouping import read_capture_time
from .filter_bar import FilterBar
from .photo_card_delegate import (
    CARD_HEIGHT,
    CARD_WIDTH,
    PhotoCardDelegate,
    ROLE_EXIF_TIME,
    ROLE_GROUP_INDEX,
    ROLE_JPG_PATH,
    ROLE_ROW,
    ROLE_THUMB,
    THUMB_BOX,
)
from .preview_window import open_in_system, show_in_explorer
from .thumbnail_gen import ThumbnailGenerator
from .utils import app_settings


class PhotoFilterProxy(QSortFilterProxyModel):
    """按综合分/场景/人物过滤,按任意列排序。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.score_min = 0
        self.score_max = 10
        self.scene = ""
        self.has_person = ""
        self.sort_col = "综合评分"
        self.sort_asc = False
        self.group_by_time = False

    # ---------- 筛选 ----------
    def set_filters(self, score_min: int, score_max: int,
                    scene: str, has_person: str):
        self.score_min = score_min
        self.score_max = score_max
        self.scene = scene
        self.has_person = has_person
        self.invalidate()  # 同时失效 filter 和 sort

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        src = self.sourceModel()
        idx = src.index(source_row, 0, source_parent)
        row = src.data(idx, ROLE_ROW) or {}
        try:
            score = float(row.get("综合评分", "") or 0)
        except (TypeError, ValueError):
            score = 0
        if not (self.score_min <= score <= self.score_max):
            return False
        if self.scene and row.get("场景", "") != self.scene:
            return False
        if self.has_person and row.get("有人", "") != self.has_person:
            return False
        return True

    # ---------- 排序 ----------
    def set_sort(self, column_name: str, ascending: bool):
        self.sort_col = column_name
        self.sort_asc = ascending
        # 分组模式下强制升序排列(group index + 时间,升序自然分组紧凑)
        if self.group_by_time:
            self.sort(0, Qt.AscendingOrder)
        else:
            self.sort(0, Qt.AscendingOrder if ascending else Qt.DescendingOrder)

    def lessThan(self, left: QModelIndex, right: QModelIndex) -> bool:
        src = self.sourceModel()
        # 分组模式:先按 group_index,再按 EXIF 时间
        if self.group_by_time:
            lg = src.data(left, ROLE_GROUP_INDEX)
            rg = src.data(right, ROLE_GROUP_INDEX)
            if isinstance(lg, int) and isinstance(rg, int) and lg != rg:
                return lg < rg
            lt = src.data(left, ROLE_EXIF_TIME)
            rt = src.data(right, ROLE_EXIF_TIME)
            if lt is not None and rt is not None:
                return lt < rt
            if lt is None and rt is not None:
                return False
            if rt is None and lt is not None:
                return True
        lrow = src.data(left, ROLE_ROW) or {}
        rrow = src.data(right, ROLE_ROW) or {}
        lv = lrow.get(self.sort_col, "") or ""
        rv = rrow.get(self.sort_col, "") or ""
        try:
            return float(lv or 0) < float(rv or 0)
        except (TypeError, ValueError):
            return str(lv) < str(rv)


class ResultsView(QWidget):
    """结果视图主体。"""

    preview_requested = Signal(object, dict)  # jpg_path, row_dict

    def __init__(self, parent=None):
        super().__init__(parent)
        self.folder: Optional[Path] = None
        self.items_by_jpg: dict[str, QStandardItem] = {}
        self._last_discard: Optional[DiscardRecord] = None
        self._batch_running: bool = False

        # 节流定时器:实时追加时避免每张都重排模型
        self._pending_refresh = False
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(200)
        self._refresh_timer.timeout.connect(self._apply_filter)

        self._build_ui()
        self._start_thumb_worker()
        self._wire()

        # 初始状态:没有文件夹,按钮大多禁用
        self.actions_bar.set_folder_available(False)

    def _build_ui(self):
        self.filter_bar = FilterBar()
        self.model = QStandardItemModel(self)
        self.proxy = PhotoFilterProxy(self)
        self.proxy.setSourceModel(self.model)
        self.proxy.set_sort("综合评分", False)

        self.view = QListView()
        self.view.setModel(self.proxy)
        self.view.setViewMode(QListView.IconMode)
        self.view.setResizeMode(QListView.Adjust)
        self.view.setMovement(QListView.Static)
        self.view.setUniformItemSizes(True)
        self.view.setSpacing(4)
        self.view.setIconSize(QSize(CARD_WIDTH, CARD_HEIGHT))
        self.view.setGridSize(QSize(CARD_WIDTH + 8, CARD_HEIGHT + 8))
        self.view.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.view.setItemDelegate(PhotoCardDelegate(self.view))
        self.view.setMouseTracking(True)
        self.view.setStyleSheet(
            "QListView { background: #F0F0F0; border: none; }"
        )

        self.actions_bar = BatchActionsBar()

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self.filter_bar)
        lay.addWidget(self.actions_bar)
        lay.addWidget(self.view, 1)

    def _start_thumb_worker(self):
        self.thumb_gen = ThumbnailGenerator(self)
        self.thumb_gen.thumb_ready.connect(self._on_thumb_ready)
        self.thumb_gen.thumb_failed.connect(self._on_thumb_failed)
        self.thumb_gen.exif_time_ready.connect(self._on_exif_time)
        self.thumb_gen.start()

    def _wire(self):
        self.filter_bar.filter_changed.connect(self._apply_filter)
        self.view.doubleClicked.connect(self._on_double_click)

        sel = self.view.selectionModel()
        if sel is not None:
            sel.selectionChanged.connect(self._on_selection_changed)

        self.actions_bar.discard_requested.connect(self.discard_selected)
        self.actions_bar.export_requested.connect(self.export_selected)
        self.actions_bar.compare_requested.connect(self.compare_selected)
        self.actions_bar.undo_requested.connect(self.undo_last_discard)
        self.actions_bar.open_csv_requested.connect(self.open_csv_file)
        self.actions_bar.show_in_explorer_requested.connect(self.open_folder_in_explorer)

        # Delete 键 = 淘汰选中,只在 view 获得焦点时生效(防止在输入框里误触发)
        sc_delete = QShortcut(QKeySequence.Delete, self.view)
        sc_delete.setContext(Qt.WidgetWithChildrenShortcut)
        sc_delete.activated.connect(self.discard_selected)

    def shutdown(self):
        """关闭时调用,让缩略图线程退出。"""
        if self.thumb_gen.isRunning():
            self.thumb_gen.stop()
            self.thumb_gen.wait(3000)

    # ---------- 数据加载 ----------
    def set_folder(self, folder: Path):
        """切换到新文件夹:清空 → 从最新 CSV 加载。"""
        self.folder = Path(folder)
        self.model.clear()
        self.items_by_jpg.clear()
        # 切目录同时要清缩略图队列,避免上一目录的生成任务拖到新目录
        self.thumb_gen.reset()
        # 跨目录的撤销记录不再有意义
        self._last_discard = None
        self.actions_bar.set_undo_available(False)
        self.actions_bar.set_folder_available(self.folder.is_dir())
        self._load_from_csv()
        self._load_folder_placeholders()
        self._apply_filter()

    def _latest_csv(self) -> Optional[Path]:
        if not self.folder:
            return None
        csvs = sorted(self.folder.glob("triage_*.csv"))
        return csvs[-1] if csvs else None

    def _load_from_csv(self):
        csv_path = self._latest_csv()
        if not csv_path or not csv_path.is_file():
            return
        try:
            with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
        except Exception as e:  # noqa: BLE001
            print(f"[ResultsView] 读 CSV 失败: {e}")
            return
        for r in rows:
            name = r.get("JPG文件名", "").strip()
            if not name:
                continue
            jpg_path = self.folder / name
            if not jpg_path.is_file():
                continue
            self._add_or_update(jpg_path, r)

    def _load_folder_placeholders(self):
        """未分析前也先把目录里的照片铺到网格里,让用户能看片选目录。"""
        if not self.folder or not self.folder.is_dir():
            return
        try:
            pairs = scan_folder(self.folder)
        except Exception as e:  # noqa: BLE001
            print(f"[ResultsView] 扫描目录失败: {e}")
            return
        for jpg_path, raw_path in pairs:
            if jpg_path.name in self.items_by_jpg:
                continue
            row = {
                "JPG文件名": jpg_path.name,
                "RAW文件名": raw_path.name if raw_path else "",
                "有RAW": "是" if raw_path else "否",
                "场景": "未分析",
                "拍摄意图": "",
                "主体": "等待分析",
                "综合评分": "",
                "一句话总评": "尚未运行模型分析,可先预览缩略图和原图。",
                "错误": "",
            }
            self._add_or_update(jpg_path, row)

    def append_row(self, jpg_path: Path, row: dict):
        """批处理进行中被调用,实时追加/更新一张。"""
        if self.folder is None:
            self.folder = jpg_path.parent
        self._add_or_update(jpg_path, row)
        # 节流:不马上重排,200ms 窗口内合并刷新
        if not self._refresh_timer.isActive():
            self._refresh_timer.start()

    def _add_or_update(self, jpg_path: Path, row: dict):
        key = jpg_path.name
        item = self.items_by_jpg.get(key)
        if item is None:
            item = QStandardItem()
            item.setData(str(jpg_path), ROLE_JPG_PATH)
            item.setEditable(False)
            item.setData(row, ROLE_ROW)
            item.setData(-1, ROLE_GROUP_INDEX)
            item.setData(None, ROLE_EXIF_TIME)  # 由 ThumbnailGenerator 异步回填
            item.setToolTip(self._build_tooltip(row))
            self.model.appendRow(item)
            self.items_by_jpg[key] = item
            if self.folder is not None:
                self.thumb_gen.enqueue(jpg_path, self.folder)
        else:
            item.setData(row, ROLE_ROW)
            item.setToolTip(self._build_tooltip(row))

    @staticmethod
    def _build_tooltip(row: dict) -> str:
        return (f"{row.get('JPG文件名', '')}\n"
                f"综合 {row.get('综合评分', '')} · "
                f"{row.get('场景', '')} · "
                f"{row.get('拍摄意图', '')}\n"
                f"{row.get('一句话总评', '')}")

    # ---------- 筛选 / 排序 ----------
    def _apply_filter(self):
        lo, hi = self.filter_bar.score_range()
        self.proxy.set_filters(lo, hi,
                               self.filter_bar.scene_filter(),
                               self.filter_bar.has_person_filter())
        self.proxy.group_by_time = self.filter_bar.group_by_time()
        if self.proxy.group_by_time:
            self._recompute_groups()
        col, asc = self.filter_bar.sort_key()
        self.proxy.set_sort(col, asc)
        self.filter_bar.update_count(self.proxy.rowCount(), self.model.rowCount())

    def _recompute_groups(self, gap_seconds: int = 60):
        """根据 EXIF 时间给每个 item 分配 group_index。"""
        # 收集 (item, capture_time)
        entries: list[tuple[QStandardItem, object]] = []
        for row in range(self.model.rowCount()):
            item = self.model.item(row)
            if item is None:
                continue
            t = item.data(ROLE_EXIF_TIME)
            entries.append((item, t))

        # 按时间升序(None 排最后),然后用 gap 分组
        with_t = [(it, t) for it, t in entries if t is not None]
        without_t = [it for it, t in entries if t is None]
        with_t.sort(key=lambda x: x[1])

        group_idx = 0
        last_t = None
        for item, t in with_t:
            if last_t is None or (t - last_t).total_seconds() > gap_seconds:
                # 新组(第一张不算"换组")
                if last_t is not None:
                    group_idx += 1
            item.setData(group_idx, ROLE_GROUP_INDEX)
            last_t = t

        # 没时间的统一放最后一组
        fallback = group_idx + 1
        for item in without_t:
            item.setData(fallback, ROLE_GROUP_INDEX)

    # ---------- 缩略图回调 ----------
    def _on_thumb_ready(self, src_path, cache_path):
        item = self.items_by_jpg.get(Path(src_path).name)
        if item is None:
            return
        if Path(item.data(ROLE_JPG_PATH) or "") != Path(src_path):
            return
        pm = QPixmap(str(cache_path))
        if not pm.isNull():
            # 预缩放到展示尺寸,避免 delegate 在滚动时反复 scale
            pm = pm.scaled(
                QSize(THUMB_BOX, THUMB_BOX),
                Qt.KeepAspectRatio, Qt.SmoothTransformation)
            item.setData(pm, ROLE_THUMB)

    def _on_thumb_failed(self, src_path, err: str):
        item = self.items_by_jpg.get(Path(src_path).name)
        if item is not None:
            if Path(item.data(ROLE_JPG_PATH) or "") != Path(src_path):
                return
            item.setToolTip((item.toolTip() or "") + f"\n\n[缩略图生成失败: {err}]")

    def _on_exif_time(self, src_path, t):
        item = self.items_by_jpg.get(Path(src_path).name)
        if item is not None:
            if Path(item.data(ROLE_JPG_PATH) or "") != Path(src_path):
                return
            item.setData(t, ROLE_EXIF_TIME)

    # ---------- 交互 ----------
    def _on_double_click(self, index: QModelIndex):
        src_idx = self.proxy.mapToSource(index)
        item = self.model.itemFromIndex(src_idx)
        if item is None:
            return
        jpg_str = item.data(ROLE_JPG_PATH)
        row = item.data(ROLE_ROW) or {}
        if jpg_str:
            self.preview_requested.emit(Path(jpg_str), row)

    def current_visible_items(self) -> list[tuple[Path, dict]]:
        """返回当前 proxy 下可见的所有 (jpg_path, row)。"""
        out: list[tuple[Path, dict]] = []
        for r in range(self.proxy.rowCount()):
            src_idx = self.proxy.mapToSource(self.proxy.index(r, 0))
            item = self.model.itemFromIndex(src_idx)
            if item is None:
                continue
            jpg_str = item.data(ROLE_JPG_PATH)
            row = item.data(ROLE_ROW) or {}
            if jpg_str:
                out.append((Path(jpg_str), row))
        return out

    def selected_items(self) -> list[tuple[Path, dict]]:
        """返回当前选中的 (jpg_path, row)。

        用 selectedRows 保证一行只计一次(model 当前单列,但为未来多列防守)。
        """
        out: list[tuple[Path, dict]] = []
        seen: set[str] = set()
        for idx in self.view.selectionModel().selectedRows():
            src_idx = self.proxy.mapToSource(idx)
            item = self.model.itemFromIndex(src_idx)
            if item is None:
                continue
            jpg_str = item.data(ROLE_JPG_PATH)
            row = item.data(ROLE_ROW) or {}
            if jpg_str and jpg_str not in seen:
                seen.add(jpg_str)
                out.append((Path(jpg_str), row))
        return out

    def _on_selection_changed(self, *_):
        self.actions_bar.set_selection_count(len(self.view.selectionModel().selectedRows()))

    # ---------- 批量操作 ----------
    def _remove_items(self, keys: list[str]):
        """从 model 里移除给定文件名的 items。"""
        # 按 row() 降序移除,避免索引偏移
        to_remove = []
        for k in keys:
            it = self.items_by_jpg.get(k)
            if it is not None:
                to_remove.append((it.row(), k))
        for row_num, k in sorted(to_remove, key=lambda x: -x[0]):
            self.model.removeRow(row_num)
            self.items_by_jpg.pop(k, None)

    def set_batch_running(self, running: bool):
        """批处理运行期间要禁用淘汰(避免和 XMP 写入抢文件)。"""
        self._batch_running = running
        # 按钮层的禁用:选择变化再刷一次
        if running:
            self.actions_bar.discard_btn.setEnabled(False)
            self.actions_bar.discard_btn.setToolTip("批处理进行中,暂不能淘汰")
        else:
            self.actions_bar.discard_btn.setToolTip(
                "把选中的照片连同 RAF/XMP 移到 _废片/ 子目录(可撤销)")
            # 恢复到和选择数联动的状态
            self._on_selection_changed()

    def discard_selected(self):
        """把选中的项移动到 _废片/ 子目录。"""
        if self.folder is None:
            return
        if self._batch_running:
            QMessageBox.warning(
                self, "批处理运行中",
                "批处理进行中,请等它结束后再淘汰。")
            return
        items = self.selected_items()
        if not items:
            return
        discard_dir = self.folder / DISCARD_SUBDIR
        reply = QMessageBox.question(
            self, "确认淘汰",
            f"将移动 {len(items)} 张照片(连同 RAF / XMP)到:\n\n"
            f"{discard_dir}\n\n"
            f"注意:只能撤销最近一次淘汰。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        record = discard_files(items, self.folder)
        self._last_discard = record

        # 先更新 model + filter,再弹提示;这样用户关掉弹窗看到的是已刷新的 grid
        removed_keys = [jpg.name for jpg, _ in record.rows]
        self._remove_items(removed_keys)
        self.actions_bar.set_undo_available(not record.is_empty())
        self.actions_bar.set_selection_count(0)
        self._apply_filter()

        msg = (f"已移动 {len(record.rows)} 张照片,共 {len(record.moves)} 个文件"
               f"(含 RAF / XMP)。\n目标: {discard_dir}")
        if record.skipped:
            msg += (f"\n\n跳过 {len(record.skipped)} 张(目标已存在冲突):\n"
                    + "\n".join(p.name for p in record.skipped[:5]))
            if len(record.skipped) > 5:
                msg += f"\n… 另有 {len(record.skipped) - 5} 张"
        QMessageBox.information(self, "淘汰完成", msg)

    def undo_last_discard(self):
        if self._last_discard is None or self._last_discard.is_empty():
            return
        record = self._last_discard
        restored = undo_discard(record)
        # 只把真正文件还原成功的 row 加回 grid
        restored_keys = set()
        for mv in record.moves:
            if mv.src.is_file():
                restored_keys.add(mv.src.name)
        partially_restored = []
        for jpg_path, row in record.rows:
            if jpg_path.is_file():
                self._add_or_update(jpg_path, row)
            else:
                partially_restored.append(jpg_path.name)
        self._last_discard = None
        self.actions_bar.set_undo_available(False)
        self._apply_filter()
        msg = f"还原了 {restored} 个文件。"
        if partially_restored:
            msg += (f"\n\n{len(partially_restored)} 张未完全还原"
                    "(原位置可能已被占用,请检查 _废片/ 目录)。")
        QMessageBox.information(self, "撤销完成", msg)

    def compare_selected(self):
        """弹对比窗口。"""
        items = self.selected_items()
        if not 2 <= len(items) <= 4:
            return
        win = CompareWindow(items, self)
        win.show()

    def export_selected(self):
        """复制选中项到用户选的目录。"""
        if self.folder is None:
            return
        items = self.selected_items()
        if not items:
            return
        last_export = app_settings().value("export/last_dir", str(self.folder))
        dest_str = QFileDialog.getExistingDirectory(
            self, "选择导出目录", last_export)
        if not dest_str:
            return
        dest = Path(dest_str)
        app_settings().setValue("export/last_dir", dest_str)
        jpg_n, raw_n = export_files(items, self.folder, dest, include_raw=True)
        QMessageBox.information(
            self, "导出完成",
            f"已复制 {jpg_n} 张 JPG 和 {raw_n} 个 RAF 到:\n{dest}",
        )

    def open_csv_file(self):
        csv_path = self._latest_csv()
        if csv_path and csv_path.is_file():
            open_in_system(csv_path)
        else:
            QMessageBox.warning(self, "找不到 CSV",
                                "当前目录没有 triage_*.csv 文件。")

    def open_folder_in_explorer(self):
        if self.folder and self.folder.is_dir():
            # 直接用系统关联方式打开整个目录(比 /select, 更贴近"打开文件夹")
            open_in_system(self.folder)
