"""PyQt widgets for the experimental Discord SOCKS/VLESS tunnel lane."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from ..adapters.discord_tunnel import (
    discord_tunnel_status_to_text,
    discord_tunnel_plan_to_text,
    discord_tunnel_start_to_text,
    discord_tunnel_stop_to_text,
    discord_tunnel_probe_to_text,
    discord_tunnel_https_probe_to_text,
    discord_tunnel_route_diagnose_to_text,
    discord_tunnel_tun_plan_to_text,
    discord_launch_through_socks_to_text,
    discord_proxy_route_plan_to_text,
    discord_stop_launched_to_text,
    FLATPAK_DISCORD_COMMAND,
    SUPPORTED_LAUNCH_MODES,
    preview_vless_import_text_to_text,
    tunnel_connection_import_vless_text_to_text,
    tunnel_connections_to_text,
)
from ..adapters.runtime_state import confirm_runtime_plan
from ..qt_compat import require_pyqt

TUNNEL_START_PLAN_ID = "runtime-default-discord-tunnel-socks-start-plan"


def make_tunnel_page(root: Path | None = None) -> Any:
    """Create the Tunnel tab without privileged actions or raw URI logging."""

    _QtCore, QtWidgets = require_pyqt()
    page = QtWidgets.QWidget()
    layout = QtWidgets.QVBoxLayout(page)
    layout.setContentsMargins(14, 14, 14, 14)
    layout.setSpacing(10)

    title = QtWidgets.QLabel("Туннель Discord")
    title.setObjectName("pageTitle")
    intro = QtWidgets.QLabel(
        "SOCKS/VLESS-ветка для Discord: импорт connection profiles, запуск внешнего core, "
        "probe через локальный SOCKS и запуск Discord через этот SOCKS. GUI не скачивает core, "
        "не меняет firewall и не печатает VLESS URI в отчёты."
    )
    intro.setWordWrap(True)

    output = QtWidgets.QPlainTextEdit()
    output.setReadOnly(True)
    output.setMinimumHeight(300)
    try:
        output.setLineWrapMode(QtWidgets.QPlainTextEdit.LineWrapMode.WidgetWidth)
    except Exception:  # pragma: no cover
        pass

    def run_action(label: str, callback: Callable[[], str]) -> None:
        try:
            output.setPlainText(callback())
        except Exception as exc:  # pragma: no cover - GUI diagnostic path
            output.setPlainText(f"{label}: ошибка\n{exc}")

    import_box = QtWidgets.QGroupBox("VLESS import")
    import_layout = QtWidgets.QVBoxLayout(import_box)
    import_layout.setSpacing(8)

    import_hint = QtWidgets.QLabel(
        "Удобный режим по образцу v2rayNG: скопируй один или несколько vless:// links, "
        "затем нажми «Импорт из буфера». Поддерживаются plain text и base64 subscription text. "
        "После импорта поле очищается; в output остаётся только redacted summary."
    )
    import_hint.setWordWrap(True)

    manual_input = QtWidgets.QPlainTextEdit()
    manual_input.setObjectName("vlessImportInput")
    manual_input.setPlaceholderText("Можно вставить vless://... вручную. Для более безопасного сценария используй кнопку «Импорт из буфера».")
    manual_input.setMaximumHeight(88)

    import_buttons = QtWidgets.QHBoxLayout()
    clipboard_button = QtWidgets.QPushButton("Импорт из буфера")
    preview_button = QtWidgets.QPushButton("Проверить поле")
    import_text_button = QtWidgets.QPushButton("Импорт из поля")
    file_button = QtWidgets.QPushButton("Импорт из файла")
    clear_button = QtWidgets.QPushButton("Очистить поле")
    for button in (clipboard_button, preview_button, import_text_button, file_button, clear_button):
        import_buttons.addWidget(button)
    import_buttons.addStretch(1)

    def import_from_clipboard() -> str:
        clipboard = QtWidgets.QApplication.clipboard()
        text = clipboard.text() if clipboard is not None else ""
        result = tunnel_connection_import_vless_text_to_text(text, source="gui-clipboard", root=root)
        manual_input.clear()
        return result

    def preview_from_field() -> str:
        return preview_vless_import_text_to_text(manual_input.toPlainText(), source="gui-text-preview")

    def import_from_field() -> str:
        result = tunnel_connection_import_vless_text_to_text(manual_input.toPlainText(), source="gui-text", root=root)
        manual_input.clear()
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
        return result

    clipboard_button.clicked.connect(lambda _checked=False: run_action("Импорт из буфера", import_from_clipboard))
    preview_button.clicked.connect(lambda _checked=False: run_action("Проверить поле", preview_from_field))
    import_text_button.clicked.connect(lambda _checked=False: run_action("Импорт из поля", import_from_field))
    file_button.clicked.connect(lambda _checked=False: run_action("Импорт из файла", import_from_file))
    clear_button.clicked.connect(lambda _checked=False: manual_input.clear())

    import_layout.addWidget(import_hint)
    import_layout.addWidget(manual_input)
    import_layout.addLayout(import_buttons)

    core_box = QtWidgets.QGroupBox("Tunnel core")
    core_layout = QtWidgets.QVBoxLayout(core_box)
    core_layout.setSpacing(8)

    core_hint = QtWidgets.QLabel(
        "Сначала нужен running tunnel core: xray, v2ray или sing-box. "
        "Если profile использует type=xhttp/splithttp, обычный /usr/bin/v2ray может завершиться с "
        "unknown transport protocol. В этом случае GUI покажет stderr и попросит выбрать совместимый core или другой profile."
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
    for button in (core_plan_button, core_start_button, core_stop_button, core_probe_button):
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

    core_layout.addWidget(core_hint)
    core_layout.addLayout(core_row)
    core_layout.addLayout(core_buttons)

    launch_box = QtWidgets.QGroupBox("Маршрут через SOCKS")
    launch_layout = QtWidgets.QVBoxLayout(launch_box)
    launch_layout.setSpacing(8)

    route_hint = QtWidgets.QLabel(
        "Эта кнопка не стартует core: она запускает Discord только если tunnel core уже running и SOCKS handshake проходит. "
        "Сначала используйте блок «Tunnel core», потом запускайте Discord через SOCKS. "
        "Перед запуском GUI делает upstream HTTPS-preflight; если VLESS route закрывает TLS, Discord не запускается в retry-loop. "
        "Вывод Discord пишется в .zap2/tunnel/logs, а не спамит в терминал GUI."
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
    launch_button = QtWidgets.QPushButton("Запустить Discord через SOCKS")
    stop_discord_button = QtWidgets.QPushButton("Остановить Discord launch")
    mode_row.addWidget(mode_label)
    mode_row.addWidget(mode_combo)
    mode_row.addWidget(route_plan_button)
    mode_row.addWidget(route_diagnose_button)
    mode_row.addWidget(launch_button)
    mode_row.addWidget(stop_discord_button)
    mode_row.addStretch(1)

    route_plan_button.clicked.connect(lambda _checked=False: run_action("План маршрута", lambda: discord_proxy_route_plan_to_text(root=root)))
    route_diagnose_button.clicked.connect(lambda _checked=False: run_action("Диагноз маршрута", lambda: discord_tunnel_route_diagnose_to_text(root=root)))
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

    launch_layout.addWidget(route_hint)
    launch_layout.addLayout(command_row)
    launch_layout.addLayout(mode_row)

    actions_box = QtWidgets.QGroupBox("Профили и probes")
    actions_layout = QtWidgets.QGridLayout(actions_box)
    actions_layout.setHorizontalSpacing(8)
    actions_layout.setVerticalSpacing(8)

    actions: tuple[tuple[str, Callable[[], str]], ...] = (
        ("Статус", lambda: discord_tunnel_status_to_text(root=root)),
        ("Профили", lambda: tunnel_connections_to_text(root=root)),
        ("SOCKS probe", lambda: discord_tunnel_probe_to_text(root=root)),
        ("HTTPS probe", lambda: discord_tunnel_https_probe_to_text(root=root)),
        ("Диагноз route", lambda: discord_tunnel_route_diagnose_to_text(root=root)),
        ("TUN/TProxy план", lambda: discord_tunnel_tun_plan_to_text(root=root)),
    )
    for index, (caption, callback) in enumerate(actions):
        button = QtWidgets.QPushButton(caption)
        button.setMaximumWidth(180)
        button.clicked.connect(lambda _checked=False, c=caption, f=callback: run_action(c, f))
        actions_layout.addWidget(button, index // 3, index % 3)

    commands = QtWidgets.QLabel(
        "Guided CLI пример:\n"
        "PYTHONPATH=gui python -m zap2_gui.app --discord-tunnel-guided-run "
        "--tunnel-core-binary /path/to/xray\n\n"
        "GUI-импорт только сохраняет/выбирает connection profile. Запуск внешнего core "
        "и Discord остаётся отдельным owner-confirmed действием."
    )
    commands.setWordWrap(True)
    commands.setObjectName("commandHint")

    layout.addWidget(title)
    layout.addWidget(intro)
    layout.addWidget(import_box)
    layout.addWidget(core_box)
    layout.addWidget(launch_box)
    layout.addWidget(actions_box)
    layout.addWidget(commands)
    layout.addWidget(output, 1)
    output.setPlainText(discord_tunnel_status_to_text(root=root))

    page.setStyleSheet(
        """
        QLabel#pageTitle { font-size: 20px; font-weight: 700; }
        QLabel#commandHint { padding: 8px; border-radius: 8px; background: rgba(127, 127, 127, 0.12); }
        QPlainTextEdit#vlessImportInput { font-family: monospace; }
        QLineEdit#discordSocksCommand { font-family: monospace; }
        """
    )
    return page
