"""PyQt runtime logs page."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..adapters.gui_runtime_controls import gui_runtime_logs
from ..qt_compat import require_pyqt


def make_runtime_logs_page(root: Path | None = None) -> Any:
    """Create the Logs tab backed by `.zap2/runtime` files."""

    _QtCore, QtWidgets = require_pyqt()
    page = QtWidgets.QWidget()
    layout = QtWidgets.QVBoxLayout(page)

    title = QtWidgets.QLabel("Логи runtime")
    title.setObjectName("pageTitle")
    intro = QtWidgets.QLabel(
        "Здесь отображаются последние runtime events, stderr/stdout nfqws2 и tail debug-лога. "
        "Вкладка только читает `.zap2/runtime` и не выполняет privileged actions."
    )
    intro.setWordWrap(True)

    output = QtWidgets.QPlainTextEdit()
    output.setReadOnly(True)
    output.setPlainText(gui_runtime_logs(root=root))

    refresh_button = QtWidgets.QPushButton("Обновить логи")

    def refresh() -> None:
        try:
            output.setPlainText(gui_runtime_logs(root=root))
        except Exception as exc:  # pragma: no cover - GUI diagnostic path
            output.setPlainText(f"Логи runtime: ошибка\n{exc}")

    refresh_button.clicked.connect(lambda _checked=False: refresh())

    layout.addWidget(title)
    layout.addWidget(intro)
    layout.addWidget(refresh_button)
    layout.addWidget(output, 1)
    return page
