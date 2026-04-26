# -*- coding: utf-8 -*-
"""分析结果统计面板 — 分数直方图 + 场景占比 + 摘要数字。"""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from PySide6.QtCharts import (
    QBarCategoryAxis,
    QBarSeries,
    QBarSet,
    QChart,
    QChartView,
    QPieSeries,
    QValueAxis,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QGridLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from core.i18n import tr


class _Stat(QWidget):
    """一张小卡片:数值 + 标签。"""
    def __init__(self, label: str, value: str = "—", color: str = "#1976D2"):
        super().__init__()
        self.setProperty("panel", "surface")
        self.value_label = QLabel(value)
        self.value_label.setStyleSheet(
            f"QLabel {{ font-size: 26px; font-weight: 600; color: {color}; }}")
        self.label = QLabel(label)
        self.label.setStyleSheet("color: #5A6270;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(2)
        lay.addWidget(self.value_label)
        lay.addWidget(self.label)

    def set_value(self, v: str):
        self.value_label.setText(v)


class StatsPanel(QWidget):
    """基于当前 results 的统计视图。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        self.update_stats([])

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(10)

        # 第一行:摘要卡片
        self.card_total = _Stat(tr("stats.total"))
        self.card_avg = _Stat(tr("stats.average"), color="#1565C0")
        self.card_pick = _Stat(tr("stats.picks"), color="#2E7D32")
        self.card_waste = _Stat(tr("stats.discards"), color="#C62828")
        self.card_port = _Stat(tr("stats.portrait_ratio"), color="#6A1B9A")
        row = QGridLayout()
        row.setSpacing(8)
        row.addWidget(self.card_total, 0, 0)
        row.addWidget(self.card_avg, 0, 1)
        row.addWidget(self.card_pick, 0, 2)
        row.addWidget(self.card_waste, 0, 3)
        row.addWidget(self.card_port, 0, 4)
        lay.addLayout(row)

        # 第二行:图表
        self.hist_view = self._make_chart_view()
        self.pie_view = self._make_chart_view()

        chart_row = QGridLayout()
        chart_row.setSpacing(8)
        chart_row.addWidget(self.hist_view, 0, 0)
        chart_row.addWidget(self.pie_view, 0, 1)
        lay.addLayout(chart_row, 1)

    def _make_chart_view(self) -> QChartView:
        view = QChartView()
        view.setRenderHint(QPainter.Antialiasing)
        view.setStyleSheet(
            "QChartView { background: white; border: 1px solid #E0E3E8;"
            " border-radius: 6px; }")
        # 预先挂一个 chart,后续重用(避免 setChart 换新时老 chart 变孤儿内存泄漏)
        chart = QChart()
        chart.setBackgroundVisible(False)
        view.setChart(chart)
        return view

    def _reset_chart(self, view: QChartView, title: str) -> QChart:
        """清空当前 chart 的 series/axes,返回它以便重新填。"""
        chart = view.chart()
        # 清理所有 series(setParent(None) 不够,显式 removeSeries)
        for s in list(chart.series()):
            chart.removeSeries(s)
            s.deleteLater()
        # 清理所有 axes
        for a in list(chart.axes()):
            chart.removeAxis(a)
            a.deleteLater()
        chart.setTitle(title)
        return chart

    # ---------- 更新 ----------
    def update_stats(self, rows: list[dict]):
        total = len(rows)
        # _to_float 现在返回所有 >= 0 的,包括 0 分;avg 只算有效(>0)分
        all_scores = [_to_float(r.get("综合评分")) for r in rows]
        valid = [s for s in all_scores if s is not None and s > 0]
        avg = (sum(valid) / len(valid)) if valid else 0.0
        # pick / waste 基于所有非 None 分(含 0),更准确
        countable = [s for s in all_scores if s is not None]
        pick = sum(1 for s in countable if s >= 7)
        waste = sum(1 for s in countable if s <= 4)
        portraits = sum(1 for r in rows if r.get("场景") == "人像")

        self.card_total.set_value(str(total))
        self.card_avg.set_value(f"{avg:.1f}" if valid else "—")
        self.card_pick.set_value(
            f"{pick}  ({pick/total:.0%})" if total else "0")
        self.card_waste.set_value(
            f"{waste}  ({waste/total:.0%})" if total else "0")
        self.card_port.set_value(
            f"{portraits}  ({portraits/total:.0%})" if total else "0")

        self._draw_histogram(valid)
        self._draw_scene_pie(rows)

    def _draw_histogram(self, scores: list[float]):
        buckets = {str(i): 0 for i in range(1, 11)}
        for s in scores:
            key = str(min(10, max(1, int(round(s)))))
            buckets[key] += 1

        chart = self._reset_chart(self.hist_view, tr("stats.score_distribution"))
        chart.legend().setVisible(False)

        bar_set = QBarSet("")
        bar_set.append([buckets[str(i)] for i in range(1, 11)])
        bar_set.setColor(QColor("#1976D2"))
        bar_set.setBorderColor(QColor("#1976D2"))

        series = QBarSeries()
        series.append(bar_set)
        chart.addSeries(series)

        x_axis = QBarCategoryAxis()
        x_axis.append([str(i) for i in range(1, 11)])
        chart.addAxis(x_axis, Qt.AlignBottom)
        series.attachAxis(x_axis)

        y_axis = QValueAxis()
        y_max = max(buckets.values()) if buckets.values() else 1
        y_axis.setRange(0, max(1, y_max + 1))
        y_axis.setLabelFormat("%d")
        y_axis.setTickCount(min(6, y_max + 2))
        chart.addAxis(y_axis, Qt.AlignLeft)
        series.attachAxis(y_axis)

    def _draw_scene_pie(self, rows: list[dict]):
        c = Counter(r.get("场景", "") for r in rows if r.get("场景"))
        chart = self._reset_chart(self.pie_view, tr("stats.scene_distribution"))
        chart.legend().setVisible(True)
        chart.legend().setAlignment(Qt.AlignRight)

        series = QPieSeries()
        palette = ["#1976D2", "#43A047", "#6A1B9A", "#EF6C00",
                   "#C62828", "#00897B", "#546E7A", "#F9A825",
                   "#AD1457", "#5D4037", "#455A64"]
        for i, (name, cnt) in enumerate(c.most_common()):
            if not name:
                continue
            slc = series.append(f"{name} ({cnt})", cnt)
            slc.setBrush(QColor(palette[i % len(palette)]))
            slc.setLabelVisible(True)
        series.setPieSize(0.65)
        chart.addSeries(series)


def _to_float(v) -> float | None:
    """空/非数字返回 None;合法数字返回 float(含 0)。"""
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
