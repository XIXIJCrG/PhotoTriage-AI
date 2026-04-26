# -*- coding: utf-8 -*-
"""集中管理应用样式,统一视觉语言。"""
from __future__ import annotations

from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication


# 主题色
COLOR_BG = "#F5F6F8"
COLOR_SURFACE = "#FFFFFF"
COLOR_PANEL = "#FAFAFB"
COLOR_BORDER = "#E0E3E8"
COLOR_HOVER = "#EAF1FB"
COLOR_SELECTED = "#1976D2"
COLOR_TEXT = "#1F2328"
COLOR_TEXT_SUB = "#5A6270"
COLOR_TEXT_MUTED = "#8A919C"
COLOR_ACCENT = "#1976D2"
COLOR_ACCENT_HOVER = "#1565C0"
COLOR_DANGER = "#C62828"
COLOR_DANGER_HOVER = "#B71C1C"
COLOR_SUCCESS = "#2E7D32"
COLOR_WARNING = "#EF6C00"
COLOR_HIGHLIGHT_BG = "#FFF3E0"

# 星级颜色分档(同 delegate 里的 _score_color 对齐)
SCORE_COLORS = {
    8: "#2E7D32",   # 绿
    7: "#1565C0",   # 蓝
    6: "#6A1B9A",   # 紫
    5: "#EF6C00",   # 橙
    0: "#C62828",   # 红
}


APP_STYLESHEET = """
/* ==================== 全局 ==================== */
* {
    font-family: "Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI", sans-serif;
    color: #1F2328;
}

QMainWindow, QDialog {
    background: #F5F6F8;
}

QWidget {
    font-size: 13px;
}

/* ==================== 按钮 ==================== */
QPushButton {
    background: #FFFFFF;
    border: 1px solid #D0D5DC;
    border-radius: 4px;
    padding: 5px 14px;
    min-height: 20px;
    color: #1F2328;
}
QPushButton:hover {
    background: #EAF1FB;
    border-color: #1976D2;
}
QPushButton:pressed {
    background: #D6E4F5;
}
QPushButton:disabled {
    background: #F0F1F3;
    border-color: #E0E3E8;
    color: #8A919C;
}

/* 主按钮 */
QPushButton[primary="true"] {
    background: #1976D2;
    border-color: #1976D2;
    color: white;
    font-weight: 600;
}
QPushButton[primary="true"]:hover {
    background: #1565C0;
    border-color: #1565C0;
}
QPushButton[primary="true"]:disabled {
    background: #B5D1EF;
    border-color: #B5D1EF;
    color: #F0F4FA;
}

/* 危险按钮 */
QPushButton[danger="true"] {
    color: #C62828;
}
QPushButton[danger="true"]:hover {
    background: #FFEBEE;
    border-color: #C62828;
}
QPushButton[danger="true"]:disabled {
    color: #E5A4A4;
}

/* ==================== 输入控件 ==================== */
QLineEdit, QSpinBox, QComboBox {
    background: #FFFFFF;
    border: 1px solid #D0D5DC;
    border-radius: 4px;
    padding: 4px 8px;
    min-height: 20px;
    selection-background-color: #1976D2;
    selection-color: white;
}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus {
    border-color: #1976D2;
}
QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled {
    background: #F0F1F3;
    color: #8A919C;
}
QLineEdit[readOnly="true"] {
    background: #F7F8FA;
    color: #5A6270;
}

QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: right center;
    width: 22px;
    border-left: 1px solid #D0D5DC;
}
QComboBox QAbstractItemView {
    background: white;
    border: 1px solid #D0D5DC;
    selection-background-color: #EAF1FB;
    selection-color: #1F2328;
    outline: none;
    padding: 2px;
}

QSpinBox::up-button, QSpinBox::down-button { width: 16px; }

QCheckBox { spacing: 6px; }
QCheckBox::indicator {
    width: 15px; height: 15px;
    border: 1px solid #D0D5DC;
    border-radius: 3px;
    background: white;
}
QCheckBox::indicator:checked {
    background: #1976D2;
    border-color: #1976D2;
    image: url();
}
QCheckBox::indicator:hover { border-color: #1976D2; }

/* ==================== 进度条 ==================== */
QProgressBar {
    background: #F0F1F3;
    border: none;
    border-radius: 4px;
    text-align: center;
    color: #1F2328;
    height: 18px;
}
QProgressBar::chunk {
    background: #1976D2;
    border-radius: 4px;
}

/* ==================== 标签页 ==================== */
QTabWidget::pane {
    border: none;
    background: #F5F6F8;
}
QTabBar { background: transparent; }
QTabBar::tab {
    background: transparent;
    padding: 8px 18px;
    margin-right: 2px;
    color: #5A6270;
    border-bottom: 2px solid transparent;
}
QTabBar::tab:selected {
    color: #1976D2;
    border-bottom: 2px solid #1976D2;
    font-weight: 600;
}
QTabBar::tab:hover:!selected {
    color: #1F2328;
}

/* ==================== ListView / 网格 ==================== */
QListView {
    background: #F5F6F8;
    border: none;
    outline: none;
}
QListView::item { background: transparent; }

/* ==================== 菜单 ==================== */
QMenuBar {
    background: #FFFFFF;
    border-bottom: 1px solid #E0E3E8;
    padding: 2px;
}
QMenuBar::item {
    padding: 4px 10px;
    background: transparent;
    border-radius: 3px;
}
QMenuBar::item:selected {
    background: #EAF1FB;
    color: #1976D2;
}
QMenu {
    background: white;
    border: 1px solid #D0D5DC;
    padding: 4px;
}
QMenu::item {
    padding: 6px 24px 6px 20px;
    border-radius: 3px;
}
QMenu::item:selected {
    background: #EAF1FB;
    color: #1976D2;
}
QMenu::separator {
    height: 1px;
    background: #E0E3E8;
    margin: 4px 8px;
}

/* ==================== 状态栏 ==================== */
QStatusBar {
    background: #FFFFFF;
    border-top: 1px solid #E0E3E8;
    color: #5A6270;
}

/* ==================== ToolTip ==================== */
QToolTip {
    background: #1F2328;
    color: #FFFFFF;
    border: none;
    border-radius: 4px;
    padding: 6px 10px;
}

/* ==================== 滚动条 ==================== */
QScrollBar:vertical {
    background: transparent;
    width: 12px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: #C8CDD5;
    border-radius: 5px;
    min-height: 30px;
    margin: 2px;
}
QScrollBar::handle:vertical:hover { background: #A8AFB9; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
QScrollBar:horizontal {
    background: transparent;
    height: 12px;
    margin: 0;
}
QScrollBar::handle:horizontal {
    background: #C8CDD5;
    border-radius: 5px;
    min-width: 30px;
    margin: 2px;
}
QScrollBar::handle:horizontal:hover { background: #A8AFB9; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0;
}

/* ==================== 分隔线 / 框架 ==================== */
QFrame[frameShape="4"] {  /* HLine */
    background: #E0E3E8;
    max-height: 1px;
    border: none;
}

/* ==================== GroupBox ==================== */
QGroupBox {
    background: #FFFFFF;
    border: 1px solid #E0E3E8;
    border-radius: 6px;
    margin-top: 14px;
    padding: 12px;
    font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 6px;
    color: #1976D2;
}

/* ==================== 面板用的 surface ==================== */
QWidget[panel="surface"] {
    background: #FFFFFF;
    border: 1px solid #E0E3E8;
    border-radius: 6px;
}

/* ==================== 专业工作台微调 ==================== */
QPushButton {
    border-radius: 6px;
    padding: 6px 14px;
    min-height: 24px;
}
QPushButton[primary="true"] {
    background: #2563EB;
    border-color: #2563EB;
}
QPushButton[primary="true"]:hover {
    background: #1D4ED8;
    border-color: #1D4ED8;
}
QLineEdit, QSpinBox, QComboBox {
    border-radius: 6px;
    min-height: 24px;
}
QListView, QListWidget, QTreeView {
    alternate-background-color: #F8FAFC;
}
QTreeView {
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 8px;
    padding: 4px;
}
QTreeView::item {
    min-height: 24px;
    padding: 3px 6px;
    border-radius: 5px;
}
QTreeView::item:selected {
    background: #EAF2FF;
    color: #1E3A8A;
}
QListWidget#FolderHistoryList {
    background: #F8FAFC;
    border: 1px solid #E2E8F0;
    border-radius: 8px;
    padding: 4px;
}
QListWidget#FolderHistoryList::item {
    padding: 8px;
    border-radius: 6px;
}
QListWidget#FolderHistoryList::item:selected {
    background: #EAF2FF;
    color: #1E3A8A;
}
QWidget[panel="sidebar"] {
    background: #FFFFFF;
    border-right: 1px solid #E2E8F0;
}
QLabel[sectionTitle="true"] {
    color: #0F172A;
    font-size: 15px;
    font-weight: 700;
}
QLabel[subTitle="true"] {
    color: #475569;
    font-weight: 600;
    padding-top: 4px;
}
QLabel[pathLabel="true"] {
    color: #475569;
    background: #F8FAFC;
    border: 1px solid #E2E8F0;
    border-radius: 8px;
    padding: 8px;
}
QLabel[muted="true"] {
    color: #64748B;
}
QLabel[emptyState="true"] {
    color: #94A3B8;
    background: #F8FAFC;
    border: 1px dashed #CBD5E1;
    border-radius: 8px;
}
"""


def apply_app_style(app: QApplication):
    """应用全局样式。"""
    # 统一字体
    font = QFont("Microsoft YaHei UI", 9)
    app.setFont(font)
    app.setStyleSheet(APP_STYLESHEET)


def mark_primary(button):
    """把某个 QPushButton 标记成主按钮样式(蓝色填充)。"""
    button.setProperty("primary", True)
    button.style().unpolish(button)
    button.style().polish(button)


def mark_danger(button):
    """把某个 QPushButton 标记成危险按钮样式(红字)。"""
    button.setProperty("danger", True)
    button.style().unpolish(button)
    button.style().polish(button)
