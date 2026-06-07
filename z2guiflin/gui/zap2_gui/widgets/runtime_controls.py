"""PyQt widgets for owner-controlled default runtime workflow."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from ..adapters.gui_runtime_controls import (
    DEFAULT_BUILD_PLAN_ID,
    DEFAULT_START_PLAN_ID,
    DEFAULT_STOP_PLAN_ID,
    gui_confirm_plan,
    gui_default_build_deps,
    gui_default_status,
    gui_default_status_summary,
    gui_execute_default_build,
    gui_prepare_default_build,
    gui_prepare_default_start,
    gui_prepare_default_stop,
    gui_privileged_default_start_command,
    gui_privileged_default_stop_command,
    gui_runtime_commands,
    gui_runtime_logs,
    gui_toggle_default_workflow,
)
from ..qt_compat import require_pyqt


def make_runtime_control_page(root: Path | None = None) -> Any:
    """Create a compact Overview tab with one primary start/stop control."""

    _QtCore, QtWidgets = require_pyqt()
    page = QtWidgets.QWidget()
    layout = QtWidgets.QVBoxLayout(page)
    layout.setContentsMargins(14, 14, 14, 14)
    layout.setSpacing(10)

    title = QtWidgets.QLabel("Обзор")
    title.setObjectName("pageTitle")
    intro = QtWidgets.QLabel(
        "Главная кнопка запускает или останавливает Default workflow целиком: "
        "проверка, сборка при необходимости, план, подтверждение и графический sudo-запрос. "
        "Подробные шаги и ошибки выводятся ниже и во вкладке «Логи»."
    )
    intro.setWordWrap(True)

    status_row = QtWidgets.QHBoxLayout()
    status_row.setSpacing(10)

    toggle_button = QtWidgets.QPushButton()
    toggle_button.setFixedSize(46, 46)
    toggle_button.setObjectName("primaryRunButton")
    toggle_button.setToolTip("Включить/выключить Default workflow")

    indicator = QtWidgets.QLabel()
    indicator.setObjectName("runtimeStatusIndicator")
    indicator.setMinimumWidth(96)

    status_text = QtWidgets.QLabel()
    status_text.setWordWrap(True)

    refresh_button = QtWidgets.QPushButton("⟳")
    refresh_button.setFixedWidth(38)
    refresh_button.setToolTip("Обновить статус")

    logs_button = QtWidgets.QPushButton("Логи")
    logs_button.setFixedWidth(72)

    status_row.addWidget(toggle_button)
    status_row.addWidget(indicator)
    status_row.addWidget(status_text, 1)
    status_row.addWidget(refresh_button)
    status_row.addWidget(logs_button)

    output = QtWidgets.QPlainTextEdit()
    output.setReadOnly(True)
    output.setMinimumHeight(260)
    try:
        output.setLineWrapMode(QtWidgets.QPlainTextEdit.LineWrapMode.WidgetWidth)
    except Exception:  # pragma: no cover - compatibility with older Qt bindings
        pass
    output.setPlainText(gui_default_status(root=root))

    details_box = QtWidgets.QGroupBox("Диагностика и ручные шаги")
    details_layout = QtWidgets.QGridLayout(details_box)
    details_layout.setHorizontalSpacing(8)
    details_layout.setVerticalSpacing(8)

    def refresh_visual_state() -> None:
        try:
            state, label, explanation = gui_default_status_summary(root=root)
            started = state == "running"
            toggle_button.setText("■" if started else "▶")
            indicator.setText(label)
            indicator.setProperty("state", state)
            status_text.setText(explanation)
        except Exception:
            toggle_button.setText("▶")
            indicator.setText("? Неизвестно")
            indicator.setProperty("state", "unknown")
            status_text.setText("Статус не прочитан")
        page.style().unpolish(indicator)
        page.style().polish(indicator)

    def run_action(label: str, func: Callable[[], str]) -> None:
        try:
            output.setPlainText(func())
        except Exception as exc:  # pragma: no cover - GUI diagnostic path
            output.setPlainText(f"{label}: ошибка\n{exc}")
        finally:
            refresh_visual_state()

    def run_toggle() -> None:
        question = QtWidgets.QMessageBox.question(
            page,
            "Default workflow",
            (
                "Выполнить полный Default workflow одной кнопкой?\n\n"
                "Если выключено: GUI проверит зависимости, соберёт nfqws2 при необходимости, "
                "создаст и подтвердит start-plan, затем покажет графический sudo-запрос.\n"
                "Если включено: GUI создаст и подтвердит stop-plan, затем покажет графический sudo-запрос.\n\n"
                "Пароль не сохраняется приложением."
            ),
        )
        if question != QtWidgets.QMessageBox.StandardButton.Yes:
            output.setPlainText("Default toggle: отменено пользователем")
            refresh_visual_state()
            return
        run_action("Default toggle", lambda: gui_toggle_default_workflow(root=root))

    toggle_button.clicked.connect(lambda _checked=False: run_toggle())
    refresh_button.clicked.connect(lambda _checked=False: run_action("Статус", lambda: gui_default_status(root=root)))
    logs_button.clicked.connect(lambda _checked=False: run_action("Runtime logs", lambda: gui_runtime_logs(root=root)))

    actions: tuple[tuple[str, Callable[[], str]], ...] = (
        ("Зависимости", lambda: gui_default_build_deps(root=root)),
        ("План сборки", lambda: gui_prepare_default_build(root=root)),
        ("Подтвердить сборку", lambda: gui_confirm_plan(root=root, plan_id=DEFAULT_BUILD_PLAN_ID)),
        ("Собрать", lambda: gui_execute_default_build(root=root)),
        ("План запуска", lambda: gui_prepare_default_start(root=root)),
        ("Подтвердить запуск", lambda: gui_confirm_plan(root=root, plan_id=DEFAULT_START_PLAN_ID)),
        ("Команда запуска", lambda: gui_privileged_default_start_command(root=root)),
        ("План стоп", lambda: gui_prepare_default_stop(root=root)),
        ("Подтвердить стоп", lambda: gui_confirm_plan(root=root, plan_id=DEFAULT_STOP_PLAN_ID)),
        ("Команда стоп", lambda: gui_privileged_default_stop_command(root=root)),
        ("Команды", lambda: gui_runtime_commands().to_text()),
    )
    for index, (caption, callback) in enumerate(actions):
        button = QtWidgets.QPushButton(caption)
        button.setMaximumWidth(160)
        button.clicked.connect(lambda _checked=False, c=caption, f=callback: run_action(c, f))
        details_layout.addWidget(button, index // 4, index % 4)

    layout.addWidget(title)
    layout.addWidget(intro)
    layout.addLayout(status_row)
    layout.addWidget(details_box)
    layout.addWidget(output, 1)

    page.setStyleSheet(
        """
        QLabel#pageTitle { font-size: 20px; font-weight: 700; }
        QPushButton#primaryRunButton {
            font-size: 24px;
            font-weight: 700;
            border-radius: 23px;
            padding: 0;
        }
        QLabel#runtimeStatusIndicator {
            font-weight: 700;
            padding: 6px 10px;
            border-radius: 12px;
            background: rgba(127, 127, 127, 0.14);
        }
        QLabel#runtimeStatusIndicator[state="running"] {
            background: rgba(0, 180, 80, 0.18);
        }
        QLabel#runtimeStatusIndicator[state="stopped"] {
            background: rgba(180, 120, 0, 0.16);
        }
        QLabel#runtimeStatusIndicator[state="idle"] {
            background: rgba(127, 127, 127, 0.14);
        }
        QLabel#runtimeStatusIndicator[state="problem"] {
            background: rgba(210, 80, 30, 0.18);
        }
        """
    )
    refresh_visual_state()
    return page
