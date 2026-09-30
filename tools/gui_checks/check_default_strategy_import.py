#!/usr/bin/env python3
"""Проверка Stage v0.3-beta: импорт Default strategy и GUI controls."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    source_txt = ROOT / "strategies/imported/windows-default-v1-game-filter.txt"
    source_json = ROOT / "strategies/imported/windows-default-v1-game-filter.json"
    default_hosts = ROOT / "profiles/hostlists/default.hosts"
    strategy_path = ROOT / "strategies/manual-local.json"
    gui_adapter = ROOT / "gui/zap2_gui/adapters/gui_runtime_controls.py"
    gui_privilege = ROOT / "gui/zap2_gui/adapters/gui_privilege.py"
    gui_widget = ROOT / "gui/zap2_gui/widgets/runtime_controls.py"
    docs = [
        ROOT / "docs/history/stages/DEFAULT_STRATEGY_IMPORT.md",
        ROOT / "docs/history/stages/GUI_RUNTIME_CONTROLS.md",
        ROOT / "docs/history/stages/GUI_POLKIT_PRIVILEGE.md",
    ]
    for path in [source_txt, source_json, default_hosts, strategy_path, gui_adapter, gui_privilege, gui_widget, *docs]:
        if not path.exists():
            print(f"Отсутствует обязательный файл Stage 4: {path.relative_to(ROOT)}")
            return 1

    source_text = source_txt.read_text(encoding="utf-8")
    if "# Preset: Default v1 (game filter)" not in source_text or "--wf-tcp-out" not in source_text:
        print("Reference Windows Default preset не похож на исходный preset")
        return 1

    meta = json.loads(source_json.read_text(encoding="utf-8"))
    if meta.get("presetName") != "Default v1 (game filter)" or meta.get("importPolicy") != "partial-linux-bridge":
        print("Метаданные импорта Default preset некорректны")
        return 1
    if len(meta.get("hostlistRefs", [])) < 5:
        print("Метаданные Default preset не содержат ожидаемые hostlist refs")
        return 1

    strategy = json.loads(strategy_path.read_text(encoding="utf-8"))
    source = strategy.get("sourcePreset", {})
    runtime_args = strategy.get("runtimeArgs", [])
    if source.get("name") != "Default v1 (game filter)" or source.get("windowsOptionsExecuted") is not False:
        print("manual-local должен явно ссылаться на импортированный Default preset без исполнения WinDivert options")
        return 1
    if not any(arg.startswith("--lua-init=@core/zapret2/lua/zapret-lib.lua") for arg in runtime_args):
        print("runtimeArgs должны подключать zapret-lib.lua из vendored core")
        return 1
    if not any(arg.startswith("--lua-desync=") for arg in runtime_args):
        print("runtimeArgs должны содержать хотя бы один nfqws2 lua-desync")
        return 1
    if any(arg.startswith("--wf-") for arg in runtime_args):
        print("runtimeArgs не должны исполнять Windows WinDivert --wf-* параметры")
        return 1

    hosts = [line.strip() for line in default_hosts.read_text(encoding="utf-8").splitlines() if line.strip() and not line.startswith("#")]
    for required_host in ("youtube.com", "googlevideo.com", "discord.com", "telegram.org"):
        if required_host not in hosts:
            print(f"default.hosts не содержит обязательный seed-domain: {required_host}")
            return 1
    if len(hosts) < 20:
        print("default.hosts всё ещё слишком пустой для Default seed")
        return 1

    session_py = (ROOT / "gui/zap2_gui/adapters/runtime_session.py").read_text(encoding="utf-8")
    if "ZAP2_RUNTIME_DEBUG" not in session_py or "args.extend(strategy_runtime_args)" not in session_py:
        print("Session runner должен читать runtimeArgs стратегии и включать debug только явно")
        return 1

    gui_text = gui_adapter.read_text(encoding="utf-8") + "\n" + gui_privilege.read_text(encoding="utf-8") + "\n" + gui_widget.read_text(encoding="utf-8")
    for token in (
        "--default-start-plan",
        "--default-stop-plan",
        "--default-status",
        "sudo -A",
        "SUDO_ASKPASS",
        "Включить через графический запрос прав",
        "Отключить через графический запрос прав",
        "asks password in terminal: no",
        "stores password: no",
    ):
        if token not in gui_text:
            print(f"GUI controls не содержат ожидаемый token: {token}")
            return 1
    if "sudo PYTHONPATH=gui python -m zap2_gui.app --default-start" in gui_text:
        print("GUI privileged controls не должны предлагать терминальный sudo как основной путь")
        return 1

    print("Default strategy import + GUI runtime controls + sudo-askpass bridge: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
