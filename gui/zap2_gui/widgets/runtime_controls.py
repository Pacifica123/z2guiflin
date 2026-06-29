"""PyQt widgets for owner-controlled default runtime workflow."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from ..adapters.discord_pretls_guided_probe import runtime_discord_pretls_guided_probe_to_text
from ..adapters.gui_first_overview import gui_first_runtime_overview, gui_first_runtime_overview_to_text, gui_first_runtime_overview_to_table_text
from ..adapters.gui_runtime_controls import (
    gui_confirm_default_build,
    gui_confirm_default_start,
    gui_confirm_default_stop,
    gui_default_build_deps,
    gui_default_status,
    gui_default_toggle_label,
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
from ..adapters.launch_composer import (
    COMPONENT_CUSTOM,
    COMPONENT_MTPROTO,
    COMPONENT_SOCKS5,
    COMPONENT_TUNNEL_VLESS,
    COMPONENT_ZAPRET_DEFAULT,
    launch_composer_plan_to_text,
    launch_composer_start_to_text,
    launch_composer_status_to_text,
    launch_composer_stop_to_text,
)
from ..qt_compat import require_pyqt


def _is_started(root: Path | None) -> bool:
    return gui_first_runtime_overview(root=root).is_running


def _status_label_text(root: Path | None) -> str:
    state = gui_first_runtime_overview(root=root)
    if state.state == "running":
        return "Запущен: selected/prepared/running/firewall совпадают"
    if state.state == "mismatch":
        return "Есть рассинхрон выбранной, подготовленной или запущенной стратегии"
    if state.state == "partial":
        return "Частичный запуск: session и firewall не совпадают"
    if state.state == "stale":
        return "Stale runtime state: нужен сброс из GUI"
    return "Остановлен: можно включить выбранную стратегию из GUI"


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
        "Overview теперь ведёт Default workflow как GUI-first сценарий: выбранная стратегия, подготовленный plan, "
        "running session и firewall/NFQUEUE показываются одним состоянием. Plan id, nft и raw commands спрятаны в Developer mode."
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

    probe_button = QtWidgets.QPushButton("Проверить Discord")
    probe_button.setToolTip("Read-only guided probe. Если workflow не запущен, GUI покажет это без shell-команд.")

    logs_button = QtWidgets.QPushButton("Логи")
    logs_button.setFixedWidth(72)

    status_row.addWidget(toggle_button)
    status_row.addWidget(indicator)
    status_row.addWidget(status_text, 1)
    status_row.addWidget(probe_button)
    status_row.addWidget(refresh_button)
    status_row.addWidget(logs_button)

    output = QtWidgets.QPlainTextEdit()
    output.setReadOnly(True)
    output.setMinimumHeight(260)
    try:
        output.setLineWrapMode(QtWidgets.QPlainTextEdit.LineWrapMode.WidgetWidth)
    except Exception:  # pragma: no cover - compatibility with older Qt bindings
        pass
    developer_mode = QtWidgets.QCheckBox("Developer mode: raw plans/nft/log commands")
    developer_mode.setObjectName("overviewDeveloperMode")
    output.setPlainText(gui_first_runtime_overview_to_text(root=root, developer=False))

    overview_table = QtWidgets.QTableWidget(0, 4)
    overview_table.setObjectName("guiFirstOverviewTable")
    overview_table.setHorizontalHeaderLabels(["Раздел", "Поле", "Значение", "Статус"])
    try:
        overview_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        overview_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
    except AttributeError:  # pragma: no cover - PyQt5 compatibility
        overview_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        overview_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
    overview_table.setAlternatingRowColors(True)
    overview_table.setMinimumHeight(210)
    try:
        overview_table.horizontalHeader().setStretchLastSection(False)
        overview_table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        overview_table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        overview_table.horizontalHeader().setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.Stretch)
        overview_table.horizontalHeader().setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
    except Exception:  # pragma: no cover - compatibility with older Qt bindings
        pass

    overview_table_box = QtWidgets.QGroupBox("Состояние Default workflow")
    overview_table_layout = QtWidgets.QVBoxLayout(overview_table_box)
    overview_table_layout.setSpacing(6)
    table_actions = QtWidgets.QHBoxLayout()
    copy_table_button = QtWidgets.QPushButton("Копировать таблицу")
    copy_table_button.setToolTip("Скопировать видимую таблицу как plain text/TSV")
    copy_output_button = QtWidgets.QPushButton("Копировать вывод")
    copy_output_button.setToolTip("Скопировать текст из нижнего окна вывода")
    table_actions.addWidget(copy_table_button)
    table_actions.addWidget(copy_output_button)
    table_actions.addStretch(1)
    overview_table_layout.addWidget(overview_table)
    overview_table_layout.addLayout(table_actions)

    composer_box = QtWidgets.QGroupBox("Комбинированный запуск")
    composer_layout = QtWidgets.QVBoxLayout(composer_box)
    composer_layout.setSpacing(8)

    composer_hint = QtWidgets.QLabel(
        "Отметь компоненты, которые нужно пробовать вместе. Supported сейчас: Zapret default и VLESS tunnel. "
        "План/статус ничего не запускают. Start запускает только отмеченные supported-компоненты в понятном порядке."
    )
    composer_hint.setWordWrap(True)

    component_grid = QtWidgets.QGridLayout()
    component_grid.setHorizontalSpacing(12)
    component_grid.setVerticalSpacing(6)

    zapret_check = QtWidgets.QCheckBox("Zapret default")
    zapret_check.setObjectName("launchComponentZapretDefault")
    zapret_check.setChecked(True)
    zapret_check.setToolTip("Default workflow: nfqws2 + owner-rules через существующий sudo-askpass путь")

    vless_check = QtWidgets.QCheckBox("VLESS tunnel")
    vless_check.setObjectName("launchComponentTunnelVless")
    vless_check.setToolTip("External core + loopback SOCKS; нужен импортированный VLESS profile и путь к core binary")

    socks5_check = QtWidgets.QCheckBox("SOCKS5 upstream")
    socks5_check.setEnabled(False)
    socks5_check.setToolTip("Planned placeholder")
    mtproto_check = QtWidgets.QCheckBox("MTProto")
    mtproto_check.setEnabled(False)
    mtproto_check.setToolTip("Planned placeholder")
    custom_check = QtWidgets.QCheckBox("Custom")
    custom_check.setEnabled(False)
    custom_check.setToolTip("Planned placeholder")

    component_grid.addWidget(zapret_check, 0, 0)
    component_grid.addWidget(vless_check, 0, 1)
    component_grid.addWidget(socks5_check, 0, 2)
    component_grid.addWidget(mtproto_check, 1, 0)
    component_grid.addWidget(custom_check, 1, 1)

    core_row = QtWidgets.QHBoxLayout()
    core_label = QtWidgets.QLabel("VLESS core binary:")
    core_input = QtWidgets.QLineEdit()
    core_input.setObjectName("launchComposerCoreBinary")
    core_input.setPlaceholderText("/path/to/xray, v2ray или sing-box")
    core_browse = QtWidgets.QPushButton("Выбрать…")
    core_browse.setMaximumWidth(100)
    core_row.addWidget(core_label)
    core_row.addWidget(core_input, 1)
    core_row.addWidget(core_browse)

    composer_buttons = QtWidgets.QHBoxLayout()
    composer_status_button = QtWidgets.QPushButton("Статус выбранного")
    composer_plan_button = QtWidgets.QPushButton("План выбранного")
    composer_start_button = QtWidgets.QPushButton("Запустить выбранное")
    composer_stop_button = QtWidgets.QPushButton("Остановить выбранное")
    for button in (composer_status_button, composer_plan_button, composer_start_button, composer_stop_button):
        composer_buttons.addWidget(button)
    composer_buttons.addStretch(1)

    def selected_components() -> str:
        selected: list[str] = []
        if zapret_check.isChecked():
            selected.append(COMPONENT_ZAPRET_DEFAULT)
        if vless_check.isChecked():
            selected.append(COMPONENT_TUNNEL_VLESS)
        if socks5_check.isChecked():
            selected.append(COMPONENT_SOCKS5)
        if mtproto_check.isChecked():
            selected.append(COMPONENT_MTPROTO)
        if custom_check.isChecked():
            selected.append(COMPONENT_CUSTOM)
        return ",".join(selected)

    def composer_core_binary() -> str | None:
        value = core_input.text().strip()
        return value or None

    def browse_core_binary() -> None:
        filename, _selected_filter = QtWidgets.QFileDialog.getOpenFileName(
            page,
            "Выбрать tunnel core binary",
            "",
            "Executables (*)",
        )
        if filename:
            core_input.setText(filename)

    def run_composer_start() -> None:
        question = QtWidgets.QMessageBox.question(
            page,
            "Комбинированный запуск",
            (
                "Запустить отмеченные supported-компоненты?\n\n"
                "Zapret default может открыть графический sudo-запрос. "
                "VLESS tunnel запускает только внешний core без sudo. "
                "План и подробный вывод будут показаны ниже."
            ),
        )
        if question != QtWidgets.QMessageBox.StandardButton.Yes:
            output.setPlainText("Launch composer start: отменено пользователем")
            refresh_visual_state()
            return
        run_action(
            "Launch composer start",
            lambda: launch_composer_start_to_text(
                root=root,
                components=selected_components(),
                core_binary=composer_core_binary(),
            ),
        )

    def run_composer_stop() -> None:
        question = QtWidgets.QMessageBox.question(
            page,
            "Комбинированная остановка",
            "Остановить отмеченные supported-компоненты в безопасном обратном порядке?",
        )
        if question != QtWidgets.QMessageBox.StandardButton.Yes:
            output.setPlainText("Launch composer stop: отменено пользователем")
            refresh_visual_state()
            return
        run_action("Launch composer stop", lambda: launch_composer_stop_to_text(root=root, components=selected_components()))

    core_browse.clicked.connect(lambda _checked=False: browse_core_binary())
    composer_status_button.clicked.connect(lambda _checked=False: run_action("Launch composer status", lambda: launch_composer_status_to_text(root=root, components=selected_components(), core_binary=composer_core_binary())))
    composer_plan_button.clicked.connect(lambda _checked=False: run_action("Launch composer plan", lambda: launch_composer_plan_to_text(root=root, components=selected_components(), core_binary=composer_core_binary())))
    composer_start_button.clicked.connect(lambda _checked=False: run_composer_start())
    composer_stop_button.clicked.connect(lambda _checked=False: run_composer_stop())

    composer_layout.addWidget(composer_hint)
    composer_layout.addLayout(component_grid)
    composer_layout.addLayout(core_row)
    composer_layout.addLayout(composer_buttons)

    details_box = QtWidgets.QGroupBox("Developer mode: ручные детали Default workflow")
    details_layout = QtWidgets.QGridLayout(details_box)
    details_layout.setHorizontalSpacing(8)
    details_layout.setVerticalSpacing(8)

    def render_overview_table() -> None:
        overview = gui_first_runtime_overview(root=root)
        rows = overview.table_rows(developer=developer_mode.isChecked())
        overview_table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            for col_index, value in enumerate(row.as_tuple()):
                item = QtWidgets.QTableWidgetItem(value)
                if col_index == 3:
                    try:
                        item.setTextAlignment(_QtCore.Qt.AlignmentFlag.AlignCenter)
                    except AttributeError:  # pragma: no cover - PyQt5 compatibility
                        item.setTextAlignment(_QtCore.Qt.AlignCenter)
                overview_table.setItem(row_index, col_index, item)
        overview_table.resizeRowsToContents()

    def copy_text_to_clipboard(text: str, label: str) -> None:
        QtWidgets.QApplication.clipboard().setText(text)
        status_text.setText(f"Скопировано: {label}")

    def copy_current_table() -> None:
        try:
            copy_text_to_clipboard(
                gui_first_runtime_overview_to_table_text(root=root, developer=developer_mode.isChecked()),
                "таблица состояния",
            )
        except Exception as exc:  # pragma: no cover - GUI diagnostic path
            output.setPlainText(f"Копирование таблицы: ошибка\n{exc}")

    def copy_current_output() -> None:
        copy_text_to_clipboard(output.toPlainText(), "нижний текстовый вывод")

    def refresh_visual_state() -> None:
        try:
            overview = gui_first_runtime_overview(root=root)
            started = overview.is_running
            toggle_button.setText("■" if started else "▶")
            indicator.setText("● Запущен" if started else ("! Требует внимания" if overview.has_mismatch else "○ Остановлен"))
            indicator.setProperty("state", "running" if started else ("mismatch" if overview.has_mismatch else "stopped"))
            toggle_button.setToolTip(overview.primary_action_label)
            status_text.setText(_status_label_text(root))
            render_overview_table()
        except Exception:
            toggle_button.setText("▶")
            indicator.setText("? Неизвестно")
            indicator.setProperty("state", "unknown")
            status_text.setText("Статус не прочитан")
            overview_table.setRowCount(0)
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

    def run_overview_state() -> None:
        run_action("GUI overview state", lambda: gui_first_runtime_overview_to_text(root=root, developer=developer_mode.isChecked()))

    def run_discord_readiness_probe() -> None:
        run_action(
            "Discord readiness probe",
            lambda: runtime_discord_pretls_guided_probe_to_text(root=root, wait_seconds=0, interactive=False),
        )

    toggle_button.clicked.connect(lambda _checked=False: run_toggle())
    probe_button.clicked.connect(lambda _checked=False: run_discord_readiness_probe())
    refresh_button.clicked.connect(lambda _checked=False: run_overview_state())
    logs_button.clicked.connect(lambda _checked=False: run_action("Runtime logs", lambda: gui_runtime_logs(root=root)))
    copy_table_button.clicked.connect(lambda _checked=False: copy_current_table())
    copy_output_button.clicked.connect(lambda _checked=False: copy_current_output())
    developer_mode.toggled.connect(lambda _checked=False: (details_box.setVisible(developer_mode.isChecked()), refresh_visual_state()))

    actions: tuple[tuple[str, Callable[[], str]], ...] = (
        ("GUI состояние", lambda: gui_first_runtime_overview_to_text(root=root, developer=developer_mode.isChecked())),
        ("Проверить Discord", lambda: runtime_discord_pretls_guided_probe_to_text(root=root, wait_seconds=0, interactive=False)),
        ("Зависимости", lambda: gui_default_build_deps(root=root)),
        ("План сборки", lambda: gui_prepare_default_build(root=root)),
        ("Подтвердить сборку", lambda: gui_confirm_default_build(root=root)),
        ("Собрать", lambda: gui_execute_default_build(root=root)),
        ("План запуска", lambda: gui_prepare_default_start(root=root)),
        ("Подтвердить запуск", lambda: gui_confirm_default_start(root=root)),
        ("Команда запуска", lambda: gui_privileged_default_start_command(root=root)),
        ("План стоп", lambda: gui_prepare_default_stop(root=root)),
        ("Подтвердить стоп", lambda: gui_confirm_default_stop(root=root)),
        ("Команда стоп", lambda: gui_privileged_default_stop_command(root=root)),
        ("Команды", lambda: gui_runtime_commands(root=root).to_text()),
    )
    for index, (caption, callback) in enumerate(actions):
        button = QtWidgets.QPushButton(caption)
        button.setMaximumWidth(160)
        button.clicked.connect(lambda _checked=False, c=caption, f=callback: run_action(c, f))
        details_layout.addWidget(button, index // 4, index % 4)

    layout.addWidget(title)
    layout.addWidget(intro)
    layout.addWidget(composer_box)
    layout.addLayout(status_row)
    layout.addWidget(overview_table_box)
    layout.addWidget(developer_mode)
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
        QLabel#runtimeStatusIndicator[state="mismatch"] {
            background: rgba(200, 60, 40, 0.18);
        }
        """
    )
    details_box.setVisible(False)
    refresh_visual_state()
    return page
