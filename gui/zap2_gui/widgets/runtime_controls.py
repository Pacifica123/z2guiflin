"""PyQt widgets for owner-controlled default runtime workflow."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

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
    gui_overview_action_output_to_text,
    gui_privileged_discord_pretls_probe,
    write_gui_overview_action_output,
)
from ..adapters.launch_error_classifier import LaunchIssue, classify_launch_issue
from ..adapters.launch_composer import (
    COMPONENT_CUSTOM,
    COMPONENT_MTPROTO,
    COMPONENT_SOCKS5,
    COMPONENT_TUNNEL_VLESS,
    COMPONENT_ZAPRET_DEFAULT,
    launch_component_views,
    launch_composer_plan_to_text,
    launch_composer_start_to_text,
    launch_composer_status_to_text,
    launch_composer_stop_to_text,
)
from ..qt_compat import require_pyqt
from ..ui_icons import misc_icon, section_icon, tinted_misc_icon
from ..theme_profiles import theme_profile_from_settings


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
        "Overview ведёт Default workflow как GUI-first сценарий: выбранная стратегия, подготовленный plan, "
        "running session и firewall/NFQUEUE показываются таблицей. Подробный текст действий перенесён во вкладку «Логи»."
    )
    intro.setWordWrap(True)

    status_row = QtWidgets.QHBoxLayout()
    status_row.setSpacing(10)

    toggle_button = QtWidgets.QPushButton()
    settings = _QtCore.QSettings("The Grey Network", "z2guiflin")
    initial_theme = theme_profile_from_settings(settings)
    toggle_button.setIcon(tinted_misc_icon("toggle-start", initial_theme.colors["accent"], 30) or misc_icon("toggle-start"))
    toggle_button.setIconSize(_QtCore.QSize(30, 30))
    toggle_button.setFixedSize(46, 46)
    toggle_button.setObjectName("primaryRunButton")
    toggle_button.setToolTip("Включить/выключить Default workflow")

    indicator = QtWidgets.QLabel()
    indicator.setObjectName("runtimeStatusIndicator")
    indicator.setMinimumWidth(96)

    status_text = QtWidgets.QLabel()
    status_text.setWordWrap(True)

    refresh_button = QtWidgets.QPushButton(misc_icon("refresh"), "")
    refresh_button.setIconSize(_QtCore.QSize(16, 16))
    refresh_button.setFixedWidth(38)
    refresh_button.setToolTip("Обновить статус")

    probe_button = QtWidgets.QPushButton(misc_icon("probe"), "Проверить Discord")
    probe_button.setIconSize(_QtCore.QSize(16, 16))
    probe_button.setToolTip("Privileged read-only guided probe через sudo-askpass: нужен только для чтения nft counters.")

    logs_button = QtWidgets.QPushButton(section_icon("logs"), "Логи")
    logs_button.setIconSize(_QtCore.QSize(16, 16))
    logs_button.setFixedWidth(72)

    status_row.addWidget(toggle_button)
    status_row.addWidget(indicator)
    status_row.addWidget(status_text, 1)
    status_row.addWidget(probe_button)
    status_row.addWidget(refresh_button)
    status_row.addWidget(logs_button)

    launch_issue: dict[str, str] = {"short": "", "full": ""}
    launch_issue_banner = QtWidgets.QFrame()
    launch_issue_banner.setObjectName("launchIssueBanner")
    launch_issue_banner.setVisible(False)
    launch_issue_layout = QtWidgets.QHBoxLayout(launch_issue_banner)
    launch_issue_layout.setContentsMargins(10, 8, 8, 8)
    launch_issue_layout.setSpacing(8)
    launch_issue_code = QtWidgets.QLabel()
    launch_issue_code.setObjectName("launchIssueCode")
    launch_issue_message = QtWidgets.QLabel()
    launch_issue_message.setObjectName("launchIssueMessage")
    launch_issue_message.setWordWrap(True)
    copy_issue_short_button = QtWidgets.QPushButton(misc_icon("copy"), "")
    copy_issue_short_button.setIconSize(_QtCore.QSize(16, 16))
    copy_issue_short_button.setFixedWidth(30)
    copy_issue_short_button.setToolTip("Копировать короткий код ошибки")
    copy_issue_full_button = QtWidgets.QPushButton(misc_icon("details"), "")
    copy_issue_full_button.setIconSize(_QtCore.QSize(16, 16))
    copy_issue_full_button.setFixedWidth(30)
    copy_issue_full_button.setToolTip("Копировать полный текст ошибки")
    close_issue_button = QtWidgets.QPushButton("×")
    close_issue_button.setFixedWidth(28)
    close_issue_button.setToolTip("Скрыть плашку")
    launch_issue_layout.addWidget(launch_issue_code)
    launch_issue_layout.addWidget(launch_issue_message, 1)
    launch_issue_layout.addWidget(copy_issue_short_button)
    launch_issue_layout.addWidget(copy_issue_full_button)
    launch_issue_layout.addWidget(close_issue_button)

    developer_mode = QtWidgets.QCheckBox("Developer mode: raw plans/nft/log commands")
    developer_mode.setObjectName("overviewDeveloperMode")
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
    copy_table_button = QtWidgets.QPushButton(misc_icon("copy"), "Копировать таблицу")
    copy_table_button.setIconSize(_QtCore.QSize(16, 16))
    copy_table_button.setToolTip("Скопировать видимую таблицу как plain text/TSV")
    copy_last_action_button = QtWidgets.QPushButton(misc_icon("details"), "Копировать последний вывод")
    copy_last_action_button.setIconSize(_QtCore.QSize(16, 16))
    copy_last_action_button.setToolTip("Скопировать последний подробный вывод из вкладки «Логи»")
    table_actions.addWidget(copy_table_button)
    table_actions.addWidget(copy_last_action_button)
    table_actions.addStretch(1)
    overview_table_layout.addLayout(table_actions)
    overview_table_layout.addWidget(overview_table)

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
    core_input.setPlaceholderText("/path/to/xray или v2ray; sing-box пока без native config")
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

    def selected_component_rows():
        return tuple(
            row
            for row in launch_component_views(
                components=selected_components(),
                root=root,
                core_binary=composer_core_binary(),
            )
            if row.selected
        )

    def selected_components_all_running() -> bool:
        rows = selected_component_rows()
        supported_rows = [row for row in rows if row.spec.supported]
        return bool(supported_rows) and all(row.status == "running" for row in supported_rows)

    def selected_components_status_summary() -> str:
        rows = selected_component_rows()
        if not rows:
            return "Ничего не выбрано для запуска"
        return "; ".join(f"{row.spec.title}: {row.status}/{row.ready}" for row in rows if row.spec.supported)

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
            write_gui_overview_action_output(root, "default", "Launch composer start", "Launch composer start: отменено пользователем")
            status_text.setText("Отменено: подробности во вкладке «Логи»")
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
            write_gui_overview_action_output(root, "default", "Launch composer stop", "Launch composer stop: отменено пользователем")
            status_text.setText("Отменено: подробности во вкладке «Логи»")
            refresh_visual_state()
            return
        run_action("Launch composer stop", lambda: launch_composer_stop_to_text(root=root, components=selected_components()))

    core_browse.clicked.connect(lambda _checked=False: browse_core_binary())
    composer_status_button.clicked.connect(lambda _checked=False: run_action("Launch composer status", lambda: launch_composer_status_to_text(root=root, components=selected_components(), core_binary=composer_core_binary())))
    composer_plan_button.clicked.connect(lambda _checked=False: run_action("Launch composer plan", lambda: launch_composer_plan_to_text(root=root, components=selected_components(), core_binary=composer_core_binary())))
    composer_start_button.clicked.connect(lambda _checked=False: run_composer_start())
    composer_stop_button.clicked.connect(lambda _checked=False: run_composer_stop())
    zapret_check.toggled.connect(lambda _checked=False: refresh_visual_state())
    vless_check.toggled.connect(lambda _checked=False: refresh_visual_state())
    core_input.textChanged.connect(lambda _text="": refresh_visual_state())

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
            status_text.setText(f"Копирование таблицы: ошибка: {exc}")

    def copy_last_action_output() -> None:
        copy_text_to_clipboard(gui_overview_action_output_to_text(root=root), "последний подробный вывод")

    def show_launch_issue(issue: LaunchIssue) -> None:
        launch_issue["short"] = issue.short_text()
        launch_issue["full"] = issue.full_text()
        launch_issue_code.setText(issue.code)
        launch_issue_message.setText(issue.message)
        launch_issue_banner.setProperty("severity", issue.severity)
        launch_issue_banner.setVisible(True)
        page.style().unpolish(launch_issue_banner)
        page.style().polish(launch_issue_banner)

    def hide_launch_issue() -> None:
        launch_issue_banner.setVisible(False)
        launch_issue["short"] = ""
        launch_issue["full"] = ""

    def copy_launch_issue_short() -> None:
        if launch_issue["short"]:
            copy_text_to_clipboard(launch_issue["short"], "короткая ошибка запуска")

    def copy_launch_issue_full() -> None:
        if launch_issue["full"]:
            copy_text_to_clipboard(launch_issue["full"], "полная ошибка запуска")

    def clear_launch_issue_on_input_change() -> None:
        hide_launch_issue()
        refresh_visual_state()

    def classify_current_action(label: str, *, text: str = "", error: str = "") -> LaunchIssue | None:
        try:
            return classify_launch_issue(
                action=label,
                text=text,
                error=error,
                selected_status=selected_components_status_summary(),
                all_selected_running=selected_components_all_running(),
            )
        except Exception:
            return None

    def refresh_visual_state() -> None:
        try:
            overview = gui_first_runtime_overview(root=root)
            all_selected_running = selected_components_all_running()
            selected_summary = selected_components_status_summary()
            toggle_button.setText("")
            current_theme = theme_profile_from_settings(settings)
            toggle_button.setIcon(
                tinted_misc_icon(
                    "toggle-stop" if all_selected_running else "toggle-start",
                    current_theme.colors["statusStopped"] if all_selected_running else current_theme.colors["accent"],
                    30,
                )
                or (misc_icon("toggle-stop") if all_selected_running else misc_icon("toggle-start"))
            )
            if all_selected_running:
                indicator.setText("● Всё запущено")
                indicator.setProperty("state", "running")
                toggle_button.setToolTip("Остановить выбранные компоненты")
                status_text.setText("Выбранные компоненты running: " + selected_summary)
            elif overview.has_mismatch:
                indicator.setText("! Требует внимания")
                indicator.setProperty("state", "mismatch")
                toggle_button.setToolTip("Запустить выбранные компоненты после исправления состояния")
                status_text.setText("Состояние Default workflow требует внимания; выбранные компоненты: " + selected_summary)
            else:
                indicator.setText("○ Остановлен")
                indicator.setProperty("state", "stopped")
                toggle_button.setToolTip("Запустить выбранные компоненты")
                status_text.setText("Выбранные компоненты не все running: " + selected_summary)
            render_overview_table()
        except Exception:
            toggle_button.setText("")
            current_theme = theme_profile_from_settings(settings)
            toggle_button.setIcon(tinted_misc_icon("toggle-start", current_theme.colors["accent"], 30) or misc_icon("toggle-start"))
            indicator.setText("? Неизвестно")
            indicator.setProperty("state", "unknown")
            status_text.setText("Статус не прочитан")
            overview_table.setRowCount(0)
        page.style().unpolish(indicator)
        page.style().polish(indicator)

    def run_action(label: str, func: Callable[[], str]) -> None:
        message = ""
        issue: LaunchIssue | None = None
        try:
            text = func()
            path = write_gui_overview_action_output(root, "default", label, text)
            issue = classify_current_action(label, text=text)
            if issue:
                message = f"{label}: {issue.code}; подробности во вкладке «Логи» ({path.name})"
            else:
                message = f"{label}: подробный вывод перенесён во вкладку «Логи» ({path.name})"
        except Exception as exc:  # pragma: no cover - GUI diagnostic path
            error_text = f"{label}: ошибка\n{exc}"
            path = write_gui_overview_action_output(root, "default", label, error_text)
            issue = classify_current_action(label, text=error_text, error=str(exc))
            message = f"{label}: ошибка; подробности во вкладке «Логи» ({path.name})"
            if issue:
                message = f"{label}: {issue.code}; подробности во вкладке «Логи» ({path.name})"
        finally:
            refresh_visual_state()
            if issue:
                show_launch_issue(issue)
            elif label in {"Combined toggle start", "Launch composer start"}:
                hide_launch_issue()
            if message:
                status_text.setText(message)

    def run_toggle() -> None:
        all_selected_running = selected_components_all_running()
        action_label = "Остановить выбранное" if all_selected_running else "Запустить выбранное"
        question = QtWidgets.QMessageBox.question(
            page,
            "Комбинированный запуск",
            (
                f"{action_label}: {selected_components()}?\n\n"
                "Главная кнопка работает по выбранным компонентам в блоке «Комбинированный запуск». "
                "Индикатор «Всё запущено» появляется только когда все выбранные supported-компоненты реально running.\n\n"
                "Zapret default может запросить sudo через графический askpass. VLESS tunnel стартует внешний core без sudo. "
                "Пароль не сохраняется приложением."
            ),
        )
        if question != QtWidgets.QMessageBox.StandardButton.Yes:
            write_gui_overview_action_output(root, "default", "Combined toggle", "Combined toggle: отменено пользователем")
            status_text.setText("Отменено: подробности во вкладке «Логи»")
            refresh_visual_state()
            return
        if all_selected_running:
            run_action("Combined toggle stop", lambda: launch_composer_stop_to_text(root=root, components=selected_components()))
        else:
            run_action(
                "Combined toggle start",
                lambda: launch_composer_start_to_text(
                    root=root,
                    components=selected_components(),
                    core_binary=composer_core_binary(),
                ),
            )

    def run_overview_state() -> None:
        run_action("GUI overview state", lambda: gui_first_runtime_overview_to_text(root=root, developer=developer_mode.isChecked()))

    def run_discord_readiness_probe() -> None:
        question = QtWidgets.QMessageBox.question(
            page,
            "Проверка Discord",
            (
                "Запустить read-only Discord probe через графический sudo-запрос?\n\n"
                "Повышенные права нужны только для чтения nft counters. Firewall и сервисы probe не меняет.\n"
                "После подтверждения открой Discord и оставь его открытым около 30 секунд."
            ),
        )
        if question != QtWidgets.QMessageBox.StandardButton.Yes:
            write_gui_overview_action_output(root, "default", "Discord readiness probe", "Discord readiness probe: отменено пользователем")
            status_text.setText("Discord probe отменён; подробности во вкладке «Логи»")
            refresh_visual_state()
            return
        run_action(
            "Discord readiness probe",
            lambda: gui_privileged_discord_pretls_probe(root=root, wait_seconds=30),
        )

    copy_issue_short_button.clicked.connect(lambda _checked=False: copy_launch_issue_short())
    copy_issue_full_button.clicked.connect(lambda _checked=False: copy_launch_issue_full())
    close_issue_button.clicked.connect(lambda _checked=False: hide_launch_issue())
    toggle_button.clicked.connect(lambda _checked=False: run_toggle())
    probe_button.clicked.connect(lambda _checked=False: run_discord_readiness_probe())
    refresh_button.clicked.connect(lambda _checked=False: run_overview_state())
    logs_button.clicked.connect(lambda _checked=False: run_action("Runtime logs", lambda: gui_runtime_logs(root=root)))
    copy_table_button.clicked.connect(lambda _checked=False: copy_current_table())
    copy_last_action_button.clicked.connect(lambda _checked=False: copy_last_action_output())
    zapret_check.toggled.connect(lambda _checked=False: clear_launch_issue_on_input_change())
    vless_check.toggled.connect(lambda _checked=False: clear_launch_issue_on_input_change())
    socks5_check.toggled.connect(lambda _checked=False: clear_launch_issue_on_input_change())
    mtproto_check.toggled.connect(lambda _checked=False: clear_launch_issue_on_input_change())
    custom_check.toggled.connect(lambda _checked=False: clear_launch_issue_on_input_change())
    core_input.textChanged.connect(lambda _text='': clear_launch_issue_on_input_change())
    developer_mode.toggled.connect(lambda _checked=False: (details_box.setVisible(developer_mode.isChecked()), refresh_visual_state()))

    actions: tuple[tuple[str, Callable[[], str]], ...] = (
        ("GUI состояние", lambda: gui_first_runtime_overview_to_text(root=root, developer=developer_mode.isChecked())),
        ("Проверить Discord", lambda: gui_privileged_discord_pretls_probe(root=root, wait_seconds=30)),
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
    layout.addWidget(launch_issue_banner)
    layout.addWidget(composer_box)
    layout.addLayout(status_row)
    layout.addWidget(overview_table_box)
    layout.addWidget(developer_mode)
    layout.addWidget(details_box)

    page.setStyleSheet(
        """
        QLabel#pageTitle { font-size: 20px; font-weight: 700; }
        QPushButton#primaryRunButton {
            font-size: 24px;
            font-weight: 700;
            padding: 0;
            background: transparent;
        }
        QTabBar::tab {
            padding: 8px 12px;
        }
        QLabel#launchIssueCode {
            font-family: monospace;
            font-weight: 700;
            padding: 2px 6px;
        }
        QLabel#launchIssueMessage {
            font-weight: 600;
        }
        QLabel#runtimeStatusIndicator {
            font-weight: 700;
            padding: 6px 2px;
            background: transparent;
            border: 0;
        }
        """
    )
    details_box.setVisible(False)
    refresh_visual_state()
    page.refresh_runtime_state = refresh_visual_state
    return page
