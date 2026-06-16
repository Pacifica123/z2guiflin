"""PyQt widgets for the experimental Discord SOCKS/VLESS tunnel lane."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from ..adapters.discord_tunnel import (
    discord_tunnel_status_to_text,
    discord_tunnel_probe_to_text,
    discord_tunnel_https_probe_to_text,
    discord_tunnel_tun_plan_to_text,
    tunnel_connections_to_text,
)
from ..qt_compat import require_pyqt


def make_tunnel_page(root: Path | None = None) -> Any:
    """Create a lightweight Tunnel tab without requiring privileged actions."""

    _QtCore, QtWidgets = require_pyqt()
    page = QtWidgets.QWidget()
    layout = QtWidgets.QVBoxLayout(page)
    layout.setContentsMargins(14, 14, 14, 14)
    layout.setSpacing(10)

    title = QtWidgets.QLabel("Туннель Discord")
    title.setObjectName("pageTitle")
    intro = QtWidgets.QLabel(
        "Экспериментальная SOCKS/VLESS-ветка: connection profiles, внешний core, "
        "HTTPS-over-SOCKS probe и guided запуск Discord. GUI здесь не скачивает core, "
        "не применяет firewall и не запускает sudo."
    )
    intro.setWordWrap(True)

    output = QtWidgets.QPlainTextEdit()
    output.setReadOnly(True)
    output.setMinimumHeight(320)
    try:
        output.setLineWrapMode(QtWidgets.QPlainTextEdit.LineWrapMode.WidgetWidth)
    except Exception:  # pragma: no cover
        pass

    actions_box = QtWidgets.QGroupBox("Read-only / безопасные действия")
    actions_layout = QtWidgets.QGridLayout(actions_box)
    actions_layout.setHorizontalSpacing(8)
    actions_layout.setVerticalSpacing(8)

    def run_action(label: str, callback: Callable[[], str]) -> None:
        try:
            output.setPlainText(callback())
        except Exception as exc:  # pragma: no cover - GUI diagnostic path
            output.setPlainText(f"{label}: ошибка\n{exc}")

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
        "Импорт connection profile всё ещё лучше делать из терминала через @file, "
        "чтобы не засвечивать VLESS URI в GUI history."
    )
    commands.setWordWrap(True)
    commands.setObjectName("commandHint")

    layout.addWidget(title)
    layout.addWidget(intro)
    layout.addWidget(actions_box)
    layout.addWidget(commands)
    layout.addWidget(output, 1)
    output.setPlainText(discord_tunnel_status_to_text(root=root))

    page.setStyleSheet(
        """
        QLabel#pageTitle { font-size: 20px; font-weight: 700; }
        QLabel#commandHint { padding: 8px; border-radius: 8px; background: rgba(127, 127, 127, 0.12); }
        """
    )
    return page
