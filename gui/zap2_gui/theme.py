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

QWidget#page-overview,
QWidget#page-core,
QWidget#page-strategies,
QWidget#page-diagnostics,
QWidget#page-tunnel,
QWidget#page-settings,
QWidget#page-logs,
QWidget#blockcheckLabContent {
    background: transparent;
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

QListWidget#navigationList::viewport {
    background: transparent;
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
    color: #3f3945;
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
    background: #faf8fb;
}

QPushButton, QToolButton {
    color: #3f3945;
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
    color: #9b939f;
    border-color: #e4dfe6;
}

QLineEdit, QPlainTextEdit, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {
    color: #3f3945;
    background: #fffefe;
    border: 1px solid #dcd5df;
    border-radius: 8px;
    padding: 6px 8px;
    selection-background-color: #d9cbe1;
    selection-color: #352d3a;
}

QLineEdit:disabled, QPlainTextEdit:disabled, QTextEdit:disabled,
QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {
    color: #9b939f;
    background: #f4f1f5;
}

QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus,
QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {
    border: 1px solid #aa91b8;
}

QComboBox::drop-down {
    width: 24px;
    border: 0;
    border-left: 1px solid #e2dce5;
    background: #fbf9fc;
    border-top-right-radius: 8px;
    border-bottom-right-radius: 8px;
}

QComboBox QAbstractItemView {
    color: #3f3945;
    background: #fffefe;
    selection-background-color: #d9cbe1;
    selection-color: #352d3a;
    outline: 0;
}

QCheckBox, QRadioButton {
    color: #3f3945;
    spacing: 7px;
    background: transparent;
}

QSpinBox, QDoubleSpinBox {
    padding-right: 22px;
}

QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {
    background: #fbf9fc;
    border-left: 1px solid #e2dce5;
    width: 18px;
}

QAbstractSpinBox::up-button {
    subcontrol-origin: border;
    subcontrol-position: top right;
    border-top-right-radius: 8px;
    border-bottom: 1px solid #e2dce5;
}

QAbstractSpinBox::down-button {
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    border-bottom-right-radius: 8px;
}

QTabWidget::pane {
    background: transparent;
    border: 0;
    top: 0;
}

QTabBar::tab {
    color: #4c4451;
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

QTabBar::tab:disabled {
    color: #9b939f;
    background: #f2eef3;
}

QHeaderView::section {
    color: #46404a;
    background: #eee8f1;
    border: 0;
    border-right: 1px solid #ddd5e1;
    border-bottom: 1px solid #ddd5e1;
    padding: 7px;
    font-weight: 600;
}

QTableCornerButton::section {
    background: #eee8f1;
    border: 0;
    border-right: 1px solid #ddd5e1;
    border-bottom: 1px solid #ddd5e1;
}

QTableView, QTreeView, QListView {
    color: #3f3945;
    background: #fffefe;
    alternate-background-color: #f8f5f9;
    gridline-color: #e6e0e8;
    border: 1px solid #ddd6e0;
    selection-background-color: #d9cbe1;
    selection-color: #352d3a;
    outline: 0;
}

QTableView::viewport, QTreeView::viewport, QListView::viewport {
    background: #fffefe;
}

QTableView::item, QTreeView::item, QListView::item {
    color: #3f3945;
    background: #fffefe;
}

QTableView::item:alternate, QTreeView::item:alternate, QListView::item:alternate {
    background: #f8f5f9;
}

QTableView::item:selected, QTreeView::item:selected, QListView::item:selected {
    color: #352d3a;
    background: #d9cbe1;
}

QTableView:disabled, QTreeView:disabled, QListView:disabled {
    color: #9b939f;
    background: #f4f1f5;
}

QScrollArea#blockcheckLabScrollArea,
QScrollArea#blockcheckLabScrollArea::viewport {
    background: transparent;
    border: 0;
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

QScrollBar:horizontal {
    background: transparent;
    height: 11px;
    margin: 3px;
}

QScrollBar::handle:horizontal {
    background: #cec4d3;
    min-width: 26px;
    border-radius: 4px;
}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal,
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
    background: transparent;
    width: 0;
}

QToolTip {
    background: #4a414f;
    color: #fffaff;
    border: 0;
    padding: 5px 7px;
}
"""


def _apply_light_palette(app: Any) -> None:
    """Detach Fusion widgets from the desktop dark palette."""

    # Imported only during real GUI startup; PyQt remains optional for CLI/tests.
    from PyQt6 import QtGui  # type: ignore[import-not-found]

    palette = QtGui.QPalette()
    colors = {
        QtGui.QPalette.ColorRole.Window: "#f6f3f7",
        QtGui.QPalette.ColorRole.WindowText: "#3f3945",
        QtGui.QPalette.ColorRole.Base: "#fffefe",
        QtGui.QPalette.ColorRole.AlternateBase: "#f8f5f9",
        QtGui.QPalette.ColorRole.ToolTipBase: "#4a414f",
        QtGui.QPalette.ColorRole.ToolTipText: "#fffaff",
        QtGui.QPalette.ColorRole.Text: "#3f3945",
        QtGui.QPalette.ColorRole.Button: "#eee8f1",
        QtGui.QPalette.ColorRole.ButtonText: "#3f3945",
        QtGui.QPalette.ColorRole.BrightText: "#ffffff",
        QtGui.QPalette.ColorRole.Highlight: "#d9cbe1",
        QtGui.QPalette.ColorRole.HighlightedText: "#352d3a",
        QtGui.QPalette.ColorRole.PlaceholderText: "#8f8793",
    }
    for role, value in colors.items():
        palette.setColor(role, QtGui.QColor(value))

    disabled = QtGui.QPalette.ColorGroup.Disabled
    palette.setColor(disabled, QtGui.QPalette.ColorRole.WindowText, QtGui.QColor("#9b939f"))
    palette.setColor(disabled, QtGui.QPalette.ColorRole.Text, QtGui.QColor("#9b939f"))
    palette.setColor(disabled, QtGui.QPalette.ColorRole.ButtonText, QtGui.QColor("#9b939f"))
    palette.setColor(disabled, QtGui.QPalette.ColorRole.Base, QtGui.QColor("#f4f1f5"))
    palette.setColor(disabled, QtGui.QPalette.ColorRole.Button, QtGui.QColor("#f0edf1"))
    app.setPalette(palette)


def apply_soft_pastel_theme(app: Any) -> None:
    """Apply one predictable light theme to the current QApplication."""

    _QtCore, _QtWidgets = require_pyqt()
    try:
        app.setStyle("Fusion")
    except Exception:
        pass

    _apply_light_palette(app)
    font = app.font()
    if font.pointSize() < 10:
        font.setPointSize(10)
        app.setFont(font)
    app.setStyleSheet(SOFT_PASTEL_STYLESHEET)


__all__ = ["SOFT_PASTEL_STYLESHEET", "apply_soft_pastel_theme"]
