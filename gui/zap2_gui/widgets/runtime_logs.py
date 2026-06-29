"""PyQt runtime logs page."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..adapters.gui_runtime_controls import gui_overview_action_output_to_text, gui_runtime_logs
from ..qt_compat import require_pyqt
from ..ui_icons import misc_icon, section_icon


def make_runtime_logs_page(root: Path | None = None) -> Any:
    """Create the Logs tab backed by `.zap2/runtime` files."""

    _QtCore, QtWidgets = require_pyqt()
    page = QtWidgets.QWidget()
    layout = QtWidgets.QVBoxLayout(page)

    title = QtWidgets.QLabel("Логи runtime")
    title.setObjectName("pageTitle")
    intro = QtWidgets.QLabel(
        "Здесь отображаются подробные выводы действий из Overview, последние runtime events, stderr/stdout nfqws2 и tail debug-лога. "
        "Вкладка только читает `.zap2/runtime` и не выполняет privileged actions."
    )
    intro.setWordWrap(True)

    tabs = QtWidgets.QTabWidget()
    tabs.setDocumentMode(True)

    overview_output = QtWidgets.QPlainTextEdit()
    overview_output.setReadOnly(True)
    overview_output.setPlainText(gui_overview_action_output_to_text(root=root))

    runtime_output = QtWidgets.QPlainTextEdit()
    runtime_output.setReadOnly(True)
    runtime_output.setPlainText(gui_runtime_logs(root=root))

    tabs.addTab(overview_output, misc_icon("logs-overview"), "Overview actions")
    tabs.addTab(runtime_output, misc_icon("logs-runtime"), "Runtime")

    buttons = QtWidgets.QHBoxLayout()
    refresh_button = QtWidgets.QPushButton(misc_icon("refresh"), "Обновить логи")
    copy_current_button = QtWidgets.QPushButton(misc_icon("copy"), "Копировать текущую вкладку")
    refresh_button.setIconSize(QtCore.QSize(16, 16))
    copy_current_button.setIconSize(QtCore.QSize(16, 16))
    buttons.addWidget(refresh_button)
    buttons.addWidget(copy_current_button)
    buttons.addStretch(1)

    def refresh() -> None:
        try:
            overview_output.setPlainText(gui_overview_action_output_to_text(root=root))
            runtime_output.setPlainText(gui_runtime_logs(root=root))
        except Exception as exc:  # pragma: no cover - GUI diagnostic path
            overview_output.setPlainText(f"Логи runtime: ошибка\n{exc}")

    def copy_current_tab() -> None:
        current = tabs.currentWidget()
        if current is not None and hasattr(current, "toPlainText"):
            QtWidgets.QApplication.clipboard().setText(current.toPlainText())

    refresh_button.clicked.connect(lambda _checked=False: refresh())
    copy_current_button.clicked.connect(lambda _checked=False: copy_current_tab())

    layout.addWidget(title)
    layout.addWidget(intro)
    layout.addLayout(buttons)
    layout.addWidget(tabs, 1)
    return page
