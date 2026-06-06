"""PyQt widgets for owner-controlled default runtime workflow."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from ..adapters.gui_runtime_controls import (
    DEFAULT_BUILD_PLAN_ID,
    gui_default_build_deps,
    gui_execute_default_build,
    DEFAULT_START_PLAN_ID,
    DEFAULT_STOP_PLAN_ID,
    gui_confirm_plan,
    gui_default_status,
    gui_prepare_default_build,
    gui_prepare_default_start,
    gui_prepare_default_stop,
    gui_privileged_default_start,
    gui_privileged_default_stop,
    gui_privileged_default_start_command,
    gui_privileged_default_stop_command,
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
        "подтверждают выбранный plan id и показывают статус. Privileged запуск/отключение "
        "идут через pkexec/polkit, поэтому пароль запрашивает системное графическое окно, "
        "а не терминальный sudo."
    )
    intro.setWordWrap(True)

    output = QtWidgets.QPlainTextEdit()
    output.setReadOnly(True)
    output.setPlainText(gui_default_status(root=root))

    buttons = QtWidgets.QHBoxLayout()

    def run_action(label: str, func: Callable[[], str]) -> None:
        try:
            output.setPlainText(func())
        except Exception as exc:  # pragma: no cover - GUI diagnostic path
            output.setPlainText(f"{label}: ошибка\n{exc}")

    def run_privileged_action(label: str, action_text: str, func: Callable[[], str]) -> None:
        question = QtWidgets.QMessageBox.question(
            page,
            label,
            (
                f"{action_text} через графический запрос прав polkit/pkexec?\n\n"
                "GUI не хранит пароль и не использует терминальный sudo. "
                "Перед этим должен быть создан и подтверждён соответствующий runtime plan."
            ),
        )
        if question != QtWidgets.QMessageBox.StandardButton.Yes:
            output.setPlainText(f"{label}: отменено пользователем до pkexec")
            return
        run_action(label, func)

    actions: tuple[tuple[str, Callable[[], str]], ...] = (
        ("Проверить зависимости", lambda: gui_default_build_deps(root=root)),
        ("План сборки", lambda: gui_prepare_default_build(root=root)),
        ("Подтвердить сборку", lambda: gui_confirm_plan(root=root, plan_id=DEFAULT_BUILD_PLAN_ID)),
        ("Собрать без sudo", lambda: gui_execute_default_build(root=root)),
        ("План запуска", lambda: gui_prepare_default_start(root=root)),
        ("Подтвердить запуск", lambda: gui_confirm_plan(root=root, plan_id=DEFAULT_START_PLAN_ID)),
        ("Команда запуска через pkexec", lambda: gui_privileged_default_start_command(root=root)),
        ("Статус", lambda: gui_default_status(root=root)),
        ("План отключения", lambda: gui_prepare_default_stop(root=root)),
        ("Подтвердить отключение", lambda: gui_confirm_plan(root=root, plan_id=DEFAULT_STOP_PLAN_ID)),
        ("Команда отключения через pkexec", lambda: gui_privileged_default_stop_command(root=root)),
        ("Команды", lambda: gui_runtime_commands().to_text()),
    )
    for caption, callback in actions:
        button = QtWidgets.QPushButton(caption)
        button.clicked.connect(lambda _checked=False, c=caption, f=callback: run_action(c, f))
        buttons.addWidget(button)

    privileged_buttons = QtWidgets.QHBoxLayout()
    start_button = QtWidgets.QPushButton("Включить через графический запрос прав")
    start_button.clicked.connect(
        lambda _checked=False: run_privileged_action(
            "Включить",
            "Запустить default workflow",
            lambda: gui_privileged_default_start(root=root),
        )
    )
    stop_button = QtWidgets.QPushButton("Отключить через графический запрос прав")
    stop_button.clicked.connect(
        lambda _checked=False: run_privileged_action(
            "Отключить",
            "Остановить default workflow",
            lambda: gui_privileged_default_stop(root=root),
        )
    )
    privileged_buttons.addWidget(start_button)
    privileged_buttons.addWidget(stop_button)

    layout.addWidget(title)
    layout.addWidget(intro)
    layout.addLayout(buttons)
    layout.addLayout(privileged_buttons)
    layout.addWidget(output, 1)
    return page
