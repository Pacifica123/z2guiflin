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

QWidget#page-home,
QWidget#page-overview,
QWidget#page-core,
QWidget#page-strategies,
QWidget#page-diagnostics,
QWidget#page-tunnel,
QWidget#page-settings,
QWidget#page-logs,
QWidget#blockcheckLabContent,
QWidget#homeContent {
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

QListWidget#navigationList::item:disabled {
    min-height: 18px;
    padding: 10px 10px 2px 10px;
    margin: 0;
    background: transparent;
    color: #756d7b;
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
    background: transparent;
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

QTabBar {
    qproperty-drawBase: 0;
    background: transparent;
}

QTabBar::base {
    background: transparent;
    border: 0;
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

QFrame#settingsCard {
    background: #fdfcfd;
    border: 1px solid #dfd8e3;
    border-radius: 12px;
}

QLabel#settingsCardTitle {
    color: #403648;
    font-size: 13pt;
    font-weight: 700;
    background: transparent;
}

QLabel#settingsValueHint {
    color: #756d7b;
    background: transparent;
}

QToolTip {
    background: #4a414f;
    color: #fffaff;
    border: 0;
    padding: 5px 7px;
}
"""


THEME_LIGHT = "light"
THEME_DARK = "dark"


_DARK_COLOR_REPLACEMENTS = (
    ("#f6f3f7", "#211e25"),
    ("#faf8fb", "#27232b"),
    ("#fdfcfd", "#2b2730"),
    ("#fffefe", "#242128"),
    ("#f8f5f9", "#28242c"),
    ("#f4f1f5", "#29262d"),
    ("#f2eef3", "#2b2830"),
    ("#f0edf1", "#2b2830"),
    ("#eee8f1", "#302a35"),
    ("#e5dce9", "#3a3340"),
    ("#e4dfe6", "#3b3640"),
    ("#e2dce5", "#47404c"),
    ("#dfd8e3", "#49414f"),
    ("#ded6e2", "#49414f"),
    ("#ddd6e0", "#49424f"),
    ("#ddd5e1", "#48414d"),
    ("#dcd5df", "#4b4451"),
    ("#dcd0e3", "#493b52"),
    ("#d9cde0", "#4b4054"),
    ("#d9cbe1", "#5b4765"),
    ("#d8cfdd", "#514958"),
    ("#cec4d3", "#5b5361"),
    ("#cbbfd2", "#62576a"),
    ("#aa91b8", "#ad88bd"),
    ("#9b939f", "#78717d"),
    ("#756d7b", "#aaa1af"),
    ("#55495d", "#d8cfdd"),
    ("#4c4451", "#ddd5e1"),
    ("#4a414f", "#17151a"),
    ("#493e51", "#f0e9f4"),
    ("#46404a", "#ded7e2"),
    ("#43334d", "#f6eef9"),
    ("#403648", "#f2ebf5"),
    ("#3f3945", "#ddd6e2"),
    ("#352d3a", "#fff8ff"),
    ("#fffaff", "#f7f2f9"),
    ("#e6e0e8", "#3e3943"),
    ("#fbf9fc", "#2b2730"),
)


def _dark_stylesheet(light_stylesheet: str) -> str:
    result = light_stylesheet
    for source, target in _DARK_COLOR_REPLACEMENTS:
        result = result.replace(source, target)
    return result


DARK_PASTEL_STYLESHEET = _dark_stylesheet(SOFT_PASTEL_STYLESHEET)


def normalize_theme_name(value: object) -> str:
    """Return one supported persistent theme identifier."""

    return THEME_DARK if str(value).strip().lower() == THEME_DARK else THEME_LIGHT


def _apply_palette(app: Any, theme_name: str) -> None:
    """Detach Fusion widgets from the desktop palette for either theme."""

    # Imported only during real GUI startup; PyQt remains optional for CLI/tests.
    from PyQt6 import QtGui  # type: ignore[import-not-found]

    dark = normalize_theme_name(theme_name) == THEME_DARK
    palette = QtGui.QPalette()
    colors = {
        QtGui.QPalette.ColorRole.Window: "#211e25" if dark else "#f6f3f7",
        QtGui.QPalette.ColorRole.WindowText: "#ddd6e2" if dark else "#3f3945",
        QtGui.QPalette.ColorRole.Base: "#242128" if dark else "#fffefe",
        QtGui.QPalette.ColorRole.AlternateBase: "#28242c" if dark else "#f8f5f9",
        QtGui.QPalette.ColorRole.ToolTipBase: "#17151a" if dark else "#4a414f",
        QtGui.QPalette.ColorRole.ToolTipText: "#f7f2f9" if dark else "#fffaff",
        QtGui.QPalette.ColorRole.Text: "#ddd6e2" if dark else "#3f3945",
        QtGui.QPalette.ColorRole.Button: "#302a35" if dark else "#eee8f1",
        QtGui.QPalette.ColorRole.ButtonText: "#ddd6e2" if dark else "#3f3945",
        QtGui.QPalette.ColorRole.BrightText: "#ffffff",
        QtGui.QPalette.ColorRole.Highlight: "#5b4765" if dark else "#d9cbe1",
        QtGui.QPalette.ColorRole.HighlightedText: "#fff8ff" if dark else "#352d3a",
        QtGui.QPalette.ColorRole.PlaceholderText: "#8d8492" if dark else "#8f8793",
    }
    for role, value in colors.items():
        palette.setColor(role, QtGui.QColor(value))

    disabled = QtGui.QPalette.ColorGroup.Disabled
    palette.setColor(disabled, QtGui.QPalette.ColorRole.WindowText, QtGui.QColor("#78717d" if dark else "#9b939f"))
    palette.setColor(disabled, QtGui.QPalette.ColorRole.Text, QtGui.QColor("#78717d" if dark else "#9b939f"))
    palette.setColor(disabled, QtGui.QPalette.ColorRole.ButtonText, QtGui.QColor("#78717d" if dark else "#9b939f"))
    palette.setColor(disabled, QtGui.QPalette.ColorRole.Base, QtGui.QColor("#29262d" if dark else "#f4f1f5"))
    palette.setColor(disabled, QtGui.QPalette.ColorRole.Button, QtGui.QColor("#2b2830" if dark else "#f0edf1"))
    app.setPalette(palette)


def _apply_light_palette(app: Any) -> None:
    """Compatibility wrapper used by older tests and callers."""

    _apply_palette(app, THEME_LIGHT)


def apply_application_theme(app: Any, theme_name: str) -> str:
    """Apply one supported theme and return its normalized identifier."""

    normalized = normalize_theme_name(theme_name)
    _QtCore, _QtWidgets = require_pyqt()
    try:
        app.setStyle("Fusion")
    except Exception:
        pass

    _apply_palette(app, normalized)
    font = app.font()
    if font.pointSize() < 10:
        font.setPointSize(10)
        app.setFont(font)
    app.setProperty("z2Theme", normalized)
    app.setStyleSheet(DARK_PASTEL_STYLESHEET if normalized == THEME_DARK else SOFT_PASTEL_STYLESHEET)
    return normalized


def apply_soft_pastel_theme(app: Any) -> None:
    """Compatibility wrapper for the original fixed light theme."""

    apply_application_theme(app, THEME_LIGHT)


__all__ = [
    "DARK_PASTEL_STYLESHEET",
    "SOFT_PASTEL_STYLESHEET",
    "THEME_DARK",
    "THEME_LIGHT",
    "apply_application_theme",
    "apply_soft_pastel_theme",
    "normalize_theme_name",
]
