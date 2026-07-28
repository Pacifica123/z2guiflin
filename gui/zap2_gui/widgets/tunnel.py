"""PyQt widgets for the experimental Discord SOCKS/VLESS tunnel lane."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from ..adapters.discord_tunnel import (
    FLATPAK_DISCORD_COMMAND,
    SUPPORTED_LAUNCH_MODES,
    discord_launch_through_socks_to_text,
    discord_proxy_route_plan_to_text,
    discord_stop_launched_to_text,
    discord_tunnel_https_probe_to_text,
    discord_tunnel_plan_to_text,
    discord_tunnel_probe_to_text,
    discord_tunnel_route_diagnose_to_text,
    discord_tunnel_start_to_text,
    discord_tunnel_status_to_text,
    discord_tunnel_stop_to_text,
    discord_tunnel_tun_plan_to_text,
    preview_vless_import_text_to_text,
    select_tunnel_connection,
    tunnel_connection_import_vless_text_to_text,
    tunnel_connections_table_rows,
    tunnel_connections_to_text,
)
from ..adapters.runtime_state import confirm_runtime_plan
from ..qt_compat import require_pyqt


TUNNEL_START_PLAN_ID = "runtime-default-discord-tunnel-socks-start-plan"


def make_tunnel_page(root: Path | None = None) -> Any:
    """Create the Tunnel tab as a GUI-first profile/core/route workflow."""

    _QtCore, QtWidgets = require_pyqt()
    page = QtWidgets.QWidget()
    layout = QtWidgets.QVBoxLayout(page)
    layout.setContentsMargins(14, 14, 14, 14)
    layout.setSpacing(10)

    title = QtWidgets.QLabel("Туннель Discord")
    title.setObjectName("pageTitle")
    intro = QtWidgets.QLabel(
        "SOCKS/VLESS-ветка теперь разделена на три шага: профили, tunnel core и запуск Discord через SOCKS. "
        "GUI не скачивает core, firewall не меняется, VLESS URI в отчёты не печатаются."
    )
    intro.setWordWrap(True)

    output = QtWidgets.QPlainTextEdit()
    output.setReadOnly(True)
    output.setMinimumHeight(230)
    output.setObjectName("tunnelOutput")
    try:
        output.setLineWrapMode(QtWidgets.QPlainTextEdit.LineWrapMode.WidgetWidth)
    except Exception:  # pragma: no cover
        pass

    def run_action(label: str, callback: Callable[[], str]) -> None:
        try:
            output.setPlainText(callback())
        except Exception as exc:  # pragma: no cover - GUI diagnostic path
            output.setPlainText(f"{label}: ошибка\n{exc}")

    controls_tabs = QtWidgets.QTabWidget()
    controls_tabs.setDocumentMode(True)
    controls_tabs.tabBar().setDrawBase(False)
    try:
        controls_tabs.setIconSize(_QtCore.QSize(16, 16))
    except Exception:  # pragma: no cover
        pass

    # Profiles tab
    profiles_page = QtWidgets.QWidget()
    profiles_layout = QtWidgets.QVBoxLayout(profiles_page)
    profiles_layout.setContentsMargins(8, 8, 8, 8)
    profiles_layout.setSpacing(8)

    profile_hint = QtWidgets.QLabel(
        "Импортированные VLESS-профили показаны таблицей. Сырые vless:// строки не отображаются. "
        "Выберите строку и нажмите «Сделать активным»."
    )
    profile_hint.setWordWrap(True)

    connections_table = QtWidgets.QTableWidget(0, 7)
    connections_table.setObjectName("tunnelConnectionsTable")
    connections_table.setHorizontalHeaderLabels(["Активен", "Название", "Адрес", "Transport", "Security", "Host", "ID"])
    connections_table.setMinimumHeight(155)
    try:
        connections_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        connections_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        connections_table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        header = connections_table.horizontalHeader()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
    except AttributeError:  # pragma: no cover - PyQt5 fallback
        connections_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        connections_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
    connection_rows: list[dict[str, str]] = []

    manual_input = QtWidgets.QPlainTextEdit()
    manual_input.setObjectName("vlessImportInput")
    manual_input.setPlaceholderText("Можно вставить vless://... вручную. После импорта поле очищается.")
    manual_input.setMaximumHeight(72)

    import_buttons = QtWidgets.QHBoxLayout()
    clipboard_button = QtWidgets.QPushButton("Импорт из буфера")
    preview_button = QtWidgets.QPushButton("Проверить поле")
    import_text_button = QtWidgets.QPushButton("Импорт из поля")
    file_button = QtWidgets.QPushButton("Импорт из файла")
    clear_button = QtWidgets.QPushButton("Очистить")
    select_button = QtWidgets.QPushButton("Сделать активным")
    refresh_profiles_button = QtWidgets.QPushButton("Обновить список")
    for button in (clipboard_button, preview_button, import_text_button, file_button, clear_button, select_button, refresh_profiles_button):
        import_buttons.addWidget(button)
    import_buttons.addStretch(1)

    def refresh_connections_table() -> None:
        nonlocal connection_rows
        connection_rows = list(tunnel_connections_table_rows(root=root))
        connections_table.setRowCount(len(connection_rows))
        for row_index, row in enumerate(connection_rows):
            values = [
                "●" if row.get("active") == "yes" else "",
                row.get("remarks", ""),
                row.get("destination", ""),
                row.get("transport", ""),
                row.get("security", ""),
                row.get("host", ""),
                row.get("connectionId", ""),
            ]
            for col, value in enumerate(values):
                item = QtWidgets.QTableWidgetItem(value)
                connections_table.setItem(row_index, col, item)
            if row.get("active") == "yes":
                connections_table.selectRow(row_index)
        if not connection_rows:
            connections_table.setRowCount(1)
            for col, value in enumerate(["", "Нет импортированных профилей", "", "", "", "", ""]):
                connections_table.setItem(0, col, QtWidgets.QTableWidgetItem(value))

    def selected_connection_id() -> str:
        row = connections_table.currentRow()
        if row < 0 or row >= len(connection_rows):
            return ""
        return connection_rows[row].get("connectionId", "")

    def import_from_clipboard() -> str:
        clipboard = QtWidgets.QApplication.clipboard()
        text = clipboard.text() if clipboard is not None else ""
        result = tunnel_connection_import_vless_text_to_text(text, source="gui-clipboard", root=root)
        manual_input.clear()
        refresh_connections_table()
        return result

    def preview_from_field() -> str:
        return preview_vless_import_text_to_text(manual_input.toPlainText(), source="gui-text-preview")

    def import_from_field() -> str:
        result = tunnel_connection_import_vless_text_to_text(manual_input.toPlainText(), source="gui-text", root=root)
        manual_input.clear()
        refresh_connections_table()
        return result

    def import_from_file() -> str:
        filename, _selected_filter = QtWidgets.QFileDialog.getOpenFileName(
            page,
            "Импорт VLESS из файла",
            "",
            "Text files (*.txt *.conf *.list);;All files (*)",
        )
        if not filename:
            return "VLESS import cancelled"
        path = Path(filename)
        text = path.read_text(encoding="utf-8")
        result = tunnel_connection_import_vless_text_to_text(text, source=f"gui-file:{path.name}", root=root)
        manual_input.clear()
        refresh_connections_table()
        return result

    def select_current_profile() -> str:
        connection_id = selected_connection_id()
        if not connection_id:
            return "Tunnel connection select: выберите строку профиля в таблице."
        result = select_tunnel_connection(connection_id, root=root)
        refresh_connections_table()
        return result

    clipboard_button.clicked.connect(lambda _checked=False: run_action("Импорт из буфера", import_from_clipboard))
    preview_button.clicked.connect(lambda _checked=False: run_action("Проверить поле", preview_from_field))
    import_text_button.clicked.connect(lambda _checked=False: run_action("Импорт из поля", import_from_field))
    file_button.clicked.connect(lambda _checked=False: run_action("Импорт из файла", import_from_file))
    clear_button.clicked.connect(lambda _checked=False: manual_input.clear())
    select_button.clicked.connect(lambda _checked=False: run_action("Сделать активным", select_current_profile))
    refresh_profiles_button.clicked.connect(lambda _checked=False: (refresh_connections_table(), run_action("Профили", lambda: tunnel_connections_to_text(root=root))))

    profiles_layout.addWidget(profile_hint)
    profiles_layout.addWidget(connections_table)
    profiles_layout.addWidget(manual_input)
    profiles_layout.addLayout(import_buttons)

    # Core tab
    core_page = QtWidgets.QWidget()
    core_layout = QtWidgets.QVBoxLayout(core_page)
    core_layout.setContentsMargins(8, 8, 8, 8)
    core_layout.setSpacing(8)

    core_hint = QtWidgets.QLabel(
        "Tunnel core должен быть running до запуска Discord через SOCKS. "
        "Для VLESS type=xhttp/splithttp обычный v2ray может быть несовместим; GUI покажет stderr и compatibility warning."
    )
    core_hint.setWordWrap(True)

    core_row = QtWidgets.QHBoxLayout()
    core_label = QtWidgets.QLabel("Core binary:")
    core_input = QtWidgets.QLineEdit()
    core_input.setObjectName("tunnelCoreBinary")
    core_input.setPlaceholderText("/usr/bin/xray, /usr/bin/v2ray или /usr/bin/sing-box")
    core_browse_button = QtWidgets.QPushButton("Выбрать…")
    core_row.addWidget(core_label)
    core_row.addWidget(core_input, 1)
    core_row.addWidget(core_browse_button)

    core_buttons = QtWidgets.QHBoxLayout()
    core_plan_button = QtWidgets.QPushButton("План core")
    core_start_button = QtWidgets.QPushButton("Запустить tunnel core")
    core_stop_button = QtWidgets.QPushButton("Остановить tunnel core")
    core_probe_button = QtWidgets.QPushButton("SOCKS probe")
    core_status_button = QtWidgets.QPushButton("Статус core")
    for button in (core_plan_button, core_start_button, core_stop_button, core_probe_button, core_status_button):
        core_buttons.addWidget(button)
    core_buttons.addStretch(1)

    def selected_core_binary() -> str | None:
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

    def plan_core() -> str:
        return discord_tunnel_plan_to_text(root=root, core_binary=selected_core_binary())

    def start_core() -> str:
        plan_text = discord_tunnel_plan_to_text(root=root, core_binary=selected_core_binary())
        confirm_runtime_plan(root=root, plan_id=TUNNEL_START_PLAN_ID)
        start_text = discord_tunnel_start_to_text(
            root=root,
            confirm_plan_id=TUNNEL_START_PLAN_ID,
            allow_parallel_with_zapret=True,
        )
        return "\n\n".join(
            [
                "GUI tunnel core start flow",
                "step 1: plan prepared",
                plan_text,
                "step 2: plan auto-confirmed for local core start",
                f"plan id: {TUNNEL_START_PLAN_ID}",
                "step 3: start result",
                start_text,
                "",
                "GUI next:",
                "Если start: started — нажмите SOCKS probe, затем «Запустить Discord через SOCKS».",
                "Если start: blocked/failed — исправьте core/profile compatibility; Discord запускать рано.",
            ]
        )

    core_browse_button.clicked.connect(lambda _checked=False: browse_core_binary())
    core_plan_button.clicked.connect(lambda _checked=False: run_action("План core", plan_core))
    core_start_button.clicked.connect(lambda _checked=False: run_action("Запустить tunnel core", start_core))
    core_stop_button.clicked.connect(lambda _checked=False: run_action("Остановить tunnel core", lambda: discord_tunnel_stop_to_text(root=root)))
    core_probe_button.clicked.connect(lambda _checked=False: run_action("SOCKS probe", lambda: discord_tunnel_probe_to_text(root=root)))
    core_status_button.clicked.connect(lambda _checked=False: run_action("Статус core", lambda: discord_tunnel_status_to_text(root=root)))

    core_layout.addWidget(core_hint)
    core_layout.addLayout(core_row)
    core_layout.addLayout(core_buttons)
    core_layout.addStretch(1)

    # Route tab
    route_page = QtWidgets.QWidget()
    route_layout = QtWidgets.QVBoxLayout(route_page)
    route_layout.setContentsMargins(8, 8, 8, 8)
    route_layout.setSpacing(8)

    route_hint = QtWidgets.QLabel(
        "Эти действия не стартуют core. Они используют уже running SOCKS. "
        "Если core stopped/failed, сначала вернитесь во вкладку «Tunnel core»."
    )
    route_hint.setWordWrap(True)

    command_row = QtWidgets.QHBoxLayout()
    command_label = QtWidgets.QLabel("Discord command:")
    command_input = QtWidgets.QLineEdit()
    command_input.setObjectName("discordSocksCommand")
    command_input.setText(FLATPAK_DISCORD_COMMAND)
    command_input.setPlaceholderText("discord или flatpak run com.discordapp.Discord")
    command_row.addWidget(command_label)
    command_row.addWidget(command_input, 1)

    mode_row = QtWidgets.QHBoxLayout()
    mode_label = QtWidgets.QLabel("Launch mode:")
    mode_combo = QtWidgets.QComboBox()
    mode_combo.setObjectName("discordSocksLaunchMode")
    mode_combo.addItems(list(SUPPORTED_LAUNCH_MODES))
    try:
        mode_combo.setCurrentText("socks-updater-window")
    except Exception:  # pragma: no cover
        pass
    route_plan_button = QtWidgets.QPushButton("План маршрута")
    route_diagnose_button = QtWidgets.QPushButton("Диагноз маршрута")
    https_probe_button = QtWidgets.QPushButton("HTTPS probe")
    launch_button = QtWidgets.QPushButton("Запустить Discord через SOCKS")
    stop_discord_button = QtWidgets.QPushButton("Остановить Discord launch")
    tun_plan_button = QtWidgets.QPushButton("TUN/TProxy план")
    for widget in (mode_label, mode_combo, route_plan_button, route_diagnose_button, https_probe_button, launch_button, stop_discord_button, tun_plan_button):
        mode_row.addWidget(widget)
    mode_row.addStretch(1)

    route_plan_button.clicked.connect(lambda _checked=False: run_action("План маршрута", lambda: discord_proxy_route_plan_to_text(root=root)))
    route_diagnose_button.clicked.connect(lambda _checked=False: run_action("Диагноз маршрута", lambda: discord_tunnel_route_diagnose_to_text(root=root)))
    https_probe_button.clicked.connect(lambda _checked=False: run_action("HTTPS probe", lambda: discord_tunnel_https_probe_to_text(root=root)))
    tun_plan_button.clicked.connect(lambda _checked=False: run_action("TUN/TProxy план", lambda: discord_tunnel_tun_plan_to_text(root=root)))
    launch_button.clicked.connect(
        lambda _checked=False: run_action(
            "Запустить Discord через SOCKS",
            lambda: discord_launch_through_socks_to_text(
                root=root,
                discord_binary=command_input.text().strip() or FLATPAK_DISCORD_COMMAND,
                launch_mode=str(mode_combo.currentText()),
                upstream_preflight=True,
            ),
        )
    )
    stop_discord_button.clicked.connect(lambda _checked=False: run_action("Остановить Discord launch", lambda: discord_stop_launched_to_text(root=root)))

    route_layout.addWidget(route_hint)
    route_layout.addLayout(command_row)
    route_layout.addLayout(mode_row)
    route_layout.addStretch(1)

    controls_tabs.addTab(profiles_page, "Профили VLESS")
    controls_tabs.addTab(core_page, "Tunnel core")
    controls_tabs.addTab(route_page, "Discord через SOCKS")

    layout.addWidget(title)
    layout.addWidget(intro)
    layout.addWidget(controls_tabs, 0)
    layout.addWidget(output, 1)
    output.setPlainText(discord_tunnel_status_to_text(root=root))
    refresh_connections_table()

    page.setStyleSheet(
        """
        QLabel#pageTitle { font-size: 20px; font-weight: 700; }
        QPlainTextEdit#vlessImportInput { font-family: monospace; }
        QPlainTextEdit#tunnelOutput {
            font-family: monospace;
            border-radius: 8px;
            padding: 8px;
        }
        QLineEdit#discordSocksCommand, QLineEdit#tunnelCoreBinary { font-family: monospace; }
        QTableWidget#tunnelConnectionsTable {
            gridline-color: rgba(90, 90, 90, 0.14);
        }
        """
    )
    return page
