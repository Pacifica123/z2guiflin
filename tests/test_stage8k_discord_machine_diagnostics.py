from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys

from zap2_gui.adapters.discord_machine_diagnostics import (
    discord_machine_diagnostics_command,
    discord_machine_diagnostics_tool,
    discord_machine_summary_text,
    parse_discord_machine_diagnostics_json,
)


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools/discord_machine_diagnostics.py"


def _load_tool_module():
    spec = importlib.util.spec_from_file_location("discord_machine_diagnostics_standalone", TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_standalone_tool_has_no_project_import_dependency_and_redacts_sensitive_output(tmp_path: Path) -> None:
    source = TOOL.read_text(encoding="utf-8")
    assert "from zap2_gui" not in source
    assert "import zap2_gui" not in source
    assert "PyQt" not in source

    module = _load_tool_module()
    home = tmp_path / "alice"
    home.mkdir()
    text = module.sanitize_text(
        f"{home}/.config/discord token=secret https://updates.discord.com/x?install_id=abc&token=def",
        home,
    )
    assert str(home) not in text
    assert "secret" not in text
    assert "install_id=abc" not in text
    assert "token=def" not in text
    assert "~/.config/discord" in text


def test_analysis_localizes_updater_failure_when_control_https_works() -> None:
    module = _load_tool_module()
    report = {
        "installations": {"native": [{"name": "discord", "version": "1.0"}], "flatpak": [], "snap": [], "binaries": []},
        "processes": {"items": []},
        "hostsOverrides": [],
        "environment": {"proxyEnvironment": {}, "sessionType": "x11"},
        "networkActors": {"actors": []},
        "localEvidence": {"logs": [], "journal": None},
        "network": {
            "endpoints": [
                {"id": "control-https", "http": {"ok": True}},
                {"id": "updater-manifest", "http": {"ok": False}},
                {"id": "app-api", "http": {"ok": True}},
                {"id": "gateway", "websocket": {"ok": True}},
                {"id": "cdn", "http": {"ok": True}},
                {"id": "media", "tls": [{"ok": True}]},
                {"id": "invite", "http": {"ok": True}},
            ]
        },
    }
    findings = module.analyze(report)
    by_code = {item["code"]: item for item in findings}
    assert by_code["updater-network-failure"]["severity"] == "error"
    assert "updates.discord.com" in " ".join(by_code["updater-network-failure"]["actions"])


def test_analysis_detects_stale_updater_without_main_client() -> None:
    module = _load_tool_module()
    report = {
        "installations": {"native": [{"name": "discord", "version": "1.0"}], "flatpak": [], "snap": [], "binaries": []},
        "processes": {"items": [{"pid": 10, "role": "updater", "ageSeconds": 75.0}]},
        "hostsOverrides": [],
        "environment": {"proxyEnvironment": {}, "sessionType": "x11"},
        "networkActors": {"actors": []},
        "localEvidence": {"logs": [], "journal": None},
        "network": {"endpoints": []},
    }
    findings = module.analyze(report)
    assert any(item["code"] == "updater-stuck-process" and item["severity"] == "error" for item in findings)


def test_tool_remains_executable_when_copied_outside_project(tmp_path: Path) -> None:
    copied = tmp_path / "discord_machine_diagnostics.py"
    shutil.copy2(TOOL, copied)
    env = dict(**__import__("os").environ)
    env["HOME"] = str(tmp_path / "home")
    Path(env["HOME"]).mkdir()
    completed = subprocess.run(
        [sys.executable, str(copied), "--no-network", "--json", "--timeout", "1"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=20,
        env=env,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["tool"] == "discord_machine_diagnostics"
    assert payload["schemaVersion"] == 1
    assert payload["readOnly"] is True
    assert str(Path(env["HOME"])) not in completed.stdout


def test_gui_adapter_points_to_standalone_tool_and_validates_payload() -> None:
    assert discord_machine_diagnostics_tool(ROOT) == TOOL
    command = discord_machine_diagnostics_command(ROOT, python_executable="python3", timeout_seconds=99)
    assert command[0] == "python3"
    assert command[1] == str(TOOL)
    assert "--json" in command
    assert command[-1] == "15.0"

    payload = parse_discord_machine_diagnostics_json(json.dumps({
        "tool": "discord_machine_diagnostics",
        "schemaVersion": 1,
        "summary": {"title": "Updater недоступен", "detail": "manifest failed", "actions": ["check updater"]},
    }))
    text = discord_machine_summary_text(payload)
    assert "Updater недоступен" in text
    assert "check updater" in text


def test_diagnostics_gui_has_async_probe_summary_collapsible_details_and_copy() -> None:
    source = (ROOT / "gui/zap2_gui/widgets/blockcheck_lab.py").read_text(encoding="utf-8")
    for token in (
        "discordMachineProbeButton",
        "QtCore.QProcess",
        "discord_machine_diagnostics_command",
        "discordMachineDiagnosticsDialog",
        "discordMachineSummaryFrame",
        "discordMachineDetailsToggle",
        "setCheckable(True)",
        "discordMachineTechnicalOutput",
        "Копировать техническую информацию",
        "QApplication.clipboard()",
    ):
        assert token in source


def test_discord_dialog_uses_theme_semantics_instead_of_hardcoded_colors() -> None:
    source = (ROOT / "gui/zap2_gui/theme_profiles.py").read_text(encoding="utf-8")
    for token in (
        "QPushButton#discordMachineProbeButton",
        "QDialog#discordMachineDiagnosticsDialog",
        "QFrame#discordMachineSummaryFrame",
        "QLabel#discordMachineSummarySeverity[severity=\"error\"]",
        "c['accent']",
        "c['statusWarning']",
        "c['statusRunning']",
    ):
        assert token in source
