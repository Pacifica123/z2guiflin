"""Application-wide soft pastel theme without third-party UI frameworks."""

from __future__ import annotations

from typing import Any

from .qt_compat import require_pyqt


SOFT_PASTEL_STYLESHEET = r"""
QWidget {
    color: #3f3945;
    font-size: 10pt;
}

QMainWindow, QWidget#appShell, QStackedWidget#contentStack {
    background: #f6f3f7;
}

QFrame#navigationRail {
    background: #eee8f1;
    border: 1px solid #ded6e2;
    border-radius: 14px;
}

QLabel#brandTitle {
    color: #493e51;
    font-size: 15pt;
    font-weight: 700;
    background: transparent;
}

QLabel#brandSubtitle, QLabel#navigationHint, QLabel#pageSubtitle {
    color: #756d7b;
    background: transparent;
}

QLabel#pageTitle {
    color: #403648;
    font-size: 20pt;
    font-weight: 700;
    background: transparent;
}

QListWidget#navigationList {
    background: transparent;
    border: 0;
    outline: 0;
    padding: 4px;
}

QListWidget#navigationList::item {
    min-height: 38px;
    padding: 7px 10px;
    margin: 2px 0;
    border-radius: 9px;
}

QListWidget#navigationList::item:hover {
    background: #e5dce9;
}

QListWidget#navigationList::item:selected {
    background: #dcd0e3;
    color: #43334d;
    font-weight: 700;
}

QFrame#contentSurface {
    background: #faf8fb;
    border: 1px solid #e2dce5;
    border-radius: 14px;
}

QGroupBox {
    background: #fdfcfd;
    border: 1px solid #dfd8e3;
    border-radius: 11px;
    margin-top: 13px;
    padding: 12px 10px 10px 10px;
    font-weight: 600;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 5px;
    color: #55495d;
    background: #fdfcfd;
}

QPushButton, QToolButton {
    background: #eee8f1;
    border: 1px solid #d8cfdd;
    border-radius: 8px;
    min-height: 29px;
    padding: 5px 11px;
}

QPushButton:hover, QToolButton:hover {
    background: #e5dce9;
    border-color: #cbbfd2;
}

QPushButton:pressed, QToolButton:pressed {
    background: #d9cde0;
}

QPushButton:disabled, QToolButton:disabled {
    background: #f0edf1;
    color: #aaa3ae;
    border-color: #e4dfe6;
}

QLineEdit, QPlainTextEdit, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {
    background: #fffefe;
    border: 1px solid #dcd5df;
    border-radius: 8px;
    padding: 6px 8px;
    selection-background-color: #d9cbe1;
    selection-color: #352d3a;
}

QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus,
QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {
    border: 1px solid #aa91b8;
}

QComboBox::drop-down {
    border: 0;
    width: 24px;
}

QCheckBox, QRadioButton {
    spacing: 7px;
    background: transparent;
}

QTabWidget::pane {
    background: #fdfcfd;
    border: 1px solid #dfd8e3;
    border-radius: 10px;
    top: -1px;
}

QTabBar::tab {
    background: #eee8f1;
    border: 1px solid #ded6e2;
    border-bottom: 0;
    padding: 8px 12px;
    margin-right: 3px;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
}

QTabBar::tab:selected {
    background: #fdfcfd;
    color: #43334d;
    font-weight: 700;
}

QHeaderView::section {
    background: #eee8f1;
    border: 0;
    border-right: 1px solid #ddd5e1;
    border-bottom: 1px solid #ddd5e1;
    padding: 7px;
    font-weight: 600;
}

QTableView, QTreeView, QListView {
    alternate-background-color: #f8f5f9;
    gridline-color: #e6e0e8;
}

QScrollBar:vertical {
    background: transparent;
    width: 11px;
    margin: 3px;
}

QScrollBar::handle:vertical {
    background: #cec4d3;
    min-height: 26px;
    border-radius: 4px;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: transparent;
    height: 0;
}

QToolTip {
    background: #4a414f;
    color: #fffaff;
    border: 0;
    padding: 5px 7px;
}
"""


def apply_soft_pastel_theme(app: Any) -> None:
    """Apply one predictable light theme to the current QApplication."""

    _QtCore, QtWidgets = require_pyqt()
    try:
        app.setStyle("Fusion")
    except Exception:
        pass

    font = app.font()
    if font.pointSize() < 10:
        font.setPointSize(10)
        app.setFont(font)
    app.setStyleSheet(SOFT_PASTEL_STYLESHEET)


__all__ = ["SOFT_PASTEL_STYLESHEET", "apply_soft_pastel_theme"]
