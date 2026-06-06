"""PyQt widgets for owner-controlled default runtime workflow."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from ..adapters.gui_runtime_controls import (
    DEFAULT_BUILD_PLAN_ID,
    DEFAULT_START_PLAN_ID,
    DEFAULT_STOP_PLAN_ID,
    gui_confirm_plan,
    gui_default_status,
    gui_prepare_default_build,
    gui_prepare_default_start,
    gui_prepare_default_stop,
    gui_runtime_commands,
)
from ..qt_compat import require_pyqt


def make_runtime_control_page(root: Path | None = None) -> Any:
    """Create an Overview tab with explicit build/start/stop/status controls."""

    _QtCore, QtWidgets = require_pyqt()
    page = QtWidgets.QWidget()
    layout = QtWidgets.QVBoxLayout(page)

    title = QtWidgets.QLabel("Обзор / управление default workflow")
    title.setObjectName("pageTitle")
    intro = QtWidgets.QLabel(
        "Кнопки ниже переносят CLI workflow в GUI shell: они готовят планы, "
        "подтверждают выбранный plan id и показывают статус. GUI не запускает sudo "
        "и не применяет firewall/service действия скрыто."
    )
    intro.setWordWrap(True)

    output = QtWidgets.QPlainTextEdit()
    output.setReadOnly(True)
    output.setPlainText(gui_runtime_commands().to_text())

    buttons = QtWidgets.QHBoxLayout()

    def run_action(label: str, func: Callable[[], str]) -> None:
        try:
            output.setPlainText(func())
        except Exception as exc:  # pragma: no cover - GUI diagnostic path
            output.setPlainText(f"{label}: ошибка\n{exc}")

    actions: tuple[tuple[str, Callable[[], str]], ...] = (
        ("План сборки", lambda: gui_prepare_default_build(root=root)),
        ("Подтвердить сборку", lambda: gui_confirm_plan(root=root, plan_id=DEFAULT_BUILD_PLAN_ID)),
        ("План запуска", lambda: gui_prepare_default_start(root=root)),
        ("Подтвердить запуск", lambda: gui_confirm_plan(root=root, plan_id=DEFAULT_START_PLAN_ID)),
        ("Статус", lambda: gui_default_status(root=root)),
        ("План отключения", lambda: gui_prepare_default_stop(root=root)),
        ("Подтвердить отключение", lambda: gui_confirm_plan(root=root, plan_id=DEFAULT_STOP_PLAN_ID)),
        ("Команды", lambda: gui_runtime_commands().to_text()),
    )
    for caption, callback in actions:
        button = QtWidgets.QPushButton(caption)
        button.clicked.connect(lambda _checked=False, c=caption, f=callback: run_action(c, f))
        buttons.addWidget(button)

    layout.addWidget(title)
    layout.addWidget(intro)
    layout.addLayout(buttons)
    layout.addWidget(output, 1)
    return page
