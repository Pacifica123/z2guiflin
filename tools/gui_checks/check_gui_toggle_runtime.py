#!/usr/bin/env python3
"""Проверка GUI toggle/logs и графического sudo-askpass bridge."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "gui"))

from zap2_gui.adapters.gui_privilege import build_gui_privileged_command  # noqa: E402
from zap2_gui.adapters.gui_runtime_controls import gui_default_toggle_label, gui_runtime_logs  # noqa: E402
from zap2_gui.adapters.runtime_logs import runtime_log_snapshot_to_text  # noqa: E402


def main() -> int:
    start_command = build_gui_privileged_command(root=ROOT, action="start")
    if not start_command.argv or start_command.argv[0] != "sudo" or "-A" not in start_command.argv:
        print("GUI privileged start должен использовать sudo -A")
        return 1
    if "ZAP2_GUI_PRIVILEGE_BRIDGE=sudo-askpass" not in start_command.argv:
        print("GUI start не маркирует sudo-askpass bridge")
        return 1
    if any(item.startswith("ZAP2_RUNTIME_DROP_IDENTITY=") for item in start_command.argv):
        print("GUI sudo-askpass start не должен форсировать runtime drop identity; нужен sudo-owner path")
        return 1
    if "SUDO_ASKPASS" not in start_command.env_overrides:
        print("GUI start должен подготовить SUDO_ASKPASS helper")
        return 1
    if start_command.asks_password_in_terminal or start_command.stores_password:
        print("GUI start не должен спрашивать пароль в терминале или хранить его")
        return 1
    stop_command = build_gui_privileged_command(root=ROOT, action="stop")
    if stop_command.argv[0] != "sudo" or "-A" not in stop_command.argv:
        print("GUI privileged stop должен использовать sudo -A")
        return 1
    label = gui_default_toggle_label(root=ROOT)
    if label not in {"Включить Default", "Выключить Default"}:
        print(f"Неожиданная подпись toggle: {label}")
        return 1
    logs = gui_runtime_logs(root=ROOT)
    if "Runtime logs" not in logs or "read-only: yes" not in logs:
        print("runtime logs adapter не вернул read-only summary")
        return 1

    widget_source = (ROOT / "gui" / "zap2_gui" / "widgets" / "runtime_controls.py").read_text(encoding="utf-8")
    for marker in ("primaryRunButton", "runtimeStatusIndicator", "▶", "■", "QGridLayout"):
        if marker not in widget_source:
            print(f"GUI overview не содержит compact marker: {marker}")
            return 1
    core_source = (ROOT / "core" / "zapret2" / "nfq2" / "nfqws.c").read_text(encoding="utf-8")
    if "Zap2 Linux runtime note (v0.3-beta)" not in core_source:
        print("core nfqws.c не содержит marker NFQUEUE privilege order patch")
        return 1

    direct_logs = runtime_log_snapshot_to_text(root=ROOT)
    if "executes now: no" not in direct_logs:
        print("runtime logs snapshot должен быть read-only")
        return 1
    print("GUI toggle/runtime logs + sudo askpass checks OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
