"""PyQt widgets for the experimental Discord SOCKS/VLESS tunnel lane."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from ..adapters.discord_tunnel import (
    discord_tunnel_status_to_text,
    discord_tunnel_probe_to_text,
    discord_tunnel_https_probe_to_text,
    discord_tunnel_tun_plan_to_text,
    preview_vless_import_text_to_text,
    tunnel_connection_import_vless_text_to_text,
    tunnel_connections_to_text,
)
from ..qt_compat import require_pyqt


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
        "SOCKS/VLESS-ветка для Discord: импорт connection profiles, внешний core, "
        "probe через локальный SOCKS и guided запуск из CLI. GUI не скачивает core, "
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

    actions_box = QtWidgets.QGroupBox("Профили и probes")
    actions_layout = QtWidgets.QGridLayout(actions_box)
    actions_layout.setHorizontalSpacing(8)
    actions_layout.setVerticalSpacing(8)

    actions: tuple[tuple[str, Callable[[], str]], ...] = (
        ("Статус", lambda: discord_tunnel_status_to_text(root=root)),
        ("Профили", lambda: tunnel_connections_to_text(root=root)),
        ("SOCKS probe", lambda: discord_tunnel_probe_to_text(root=root)),
        ("HTTPS probe", lambda: discord_tunnel_https_probe_to_text(root=root)),
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
    layout.addWidget(actions_box)
    layout.addWidget(commands)
    layout.addWidget(output, 1)
    output.setPlainText(discord_tunnel_status_to_text(root=root))

    page.setStyleSheet(
        """
        QLabel#pageTitle { font-size: 20px; font-weight: 700; }
        QLabel#commandHint { padding: 8px; border-radius: 8px; background: rgba(127, 127, 127, 0.12); }
        QPlainTextEdit#vlessImportInput { font-family: monospace; }
        """
    )
    return page
