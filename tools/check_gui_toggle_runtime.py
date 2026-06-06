#!/usr/bin/env python3
"""Проверка GUI toggle/logs и polkit root-preserve bridge."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "gui"))

from zap2_gui.adapters.gui_privilege import build_gui_privileged_command  # noqa: E402
from zap2_gui.adapters.gui_runtime_controls import gui_default_toggle_label, gui_runtime_logs  # noqa: E402
from zap2_gui.adapters.runtime_logs import runtime_log_snapshot_to_text  # noqa: E402


def main() -> int:
    start_command = build_gui_privileged_command(root=ROOT, action="start")
    if "ZAP2_RUNTIME_DROP_IDENTITY=polkit-root" not in start_command.argv:
        print("GUI pkexec start не передаёт polkit-root drop identity")
        return 1
    if "ZAP2_GUI_PRIVILEGE_BRIDGE=pkexec" not in start_command.argv:
        print("GUI pkexec start не маркирует privilege bridge")
        return 1
    stop_command = build_gui_privileged_command(root=ROOT, action="stop")
    if "ZAP2_RUNTIME_DROP_IDENTITY=polkit-root" in stop_command.argv:
        print("GUI pkexec stop не должен форсировать root-preserve identity")
        return 1
    label = gui_default_toggle_label(root=ROOT)
    if label not in {"Включить Default", "Выключить Default"}:
        print(f"Неожиданная подпись toggle: {label}")
        return 1
    logs = gui_runtime_logs(root=ROOT)
    if "Runtime logs" not in logs or "read-only: yes" not in logs:
        print("runtime logs adapter не вернул read-only summary")
        return 1
    direct_logs = runtime_log_snapshot_to_text(root=ROOT)
    if "executes now: no" not in direct_logs:
        print("runtime logs snapshot должен быть read-only")
        return 1
    print("GUI toggle/runtime logs checks OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
