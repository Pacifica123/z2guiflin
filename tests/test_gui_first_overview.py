from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path

from zap2_gui.adapters.gui_first_overview import gui_first_runtime_overview, gui_first_runtime_overview_to_text
from zap2_gui.adapters.runtime_default import prepare_default_workflow_plan
from zap2_gui.adapters.runtime_session import _capture_process_identity
from zap2_gui.adapters.workspace_profiles import select_workspace_strategy
from zap2_gui.app import main

ROOT = Path(__file__).resolve().parents[1]


def _copy_project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    shutil.copytree(ROOT, project, ignore=shutil.ignore_patterns(".git", ".zap2", "__pycache__", "*.pyc", ".pytest_cache"))
    return project


def test_gui_first_overview_starts_as_user_mode_no_shell_commands(tmp_path: Path) -> None:
    project = _copy_project(tmp_path)
    overview = gui_first_runtime_overview(project)
    text = overview.to_text()

    assert overview.state == "stopped"
    assert overview.primary_action == "start"
    assert "selected strategy:" in text
    assert "prepared start plan: none" in text
    assert "user mode: no shell commands are required" in text
    assert "sudo nft" not in text
    assert "PYTHONPATH=" not in text


def test_gui_first_overview_detects_stale_plan_after_strategy_change(tmp_path: Path) -> None:
    project = _copy_project(tmp_path)
    prepare_default_workflow_plan(project, action="start", profile_id="default")
    select_workspace_strategy(project, "windows-all-tcp-udp-v3-2-linux-bridge", profile_id="default")

    overview = gui_first_runtime_overview(project)
    text = overview.to_text(developer=True)

    assert overview.prepared_start_plan_state == "stale"
    assert overview.prepared_start_plan_strategy_id == "manual-local"
    assert overview.selected_strategy_id == "windows-all-tcp-udp-v3-2-linux-bridge"
    assert "Пересобрать план и включить" in text
    assert "Developer details:" in text


def test_gui_first_overview_detects_running_strategy_mismatch(tmp_path: Path) -> None:
    project = _copy_project(tmp_path)
    select_workspace_strategy(project, "windows-all-tcp-udp-v3-2-linux-bridge", profile_id="default")
    sessions = project / ".zap2/runtime/sessions"
    sessions.mkdir(parents=True, exist_ok=True)
    (sessions / "default.default-workflow.json").write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "marker": "zap2-default-workflow-v1",
                "rootPath": str(project),
                "state": "started",
                "action": "start",
                "profileId": "default",
                "strategyId": "manual-local",
                "ownerRulesResult": {"state": "applied", "message": "test"},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (sessions / "default.owner-rules.json").write_text(
        json.dumps(
            {
                "state": "applied",
                "strategyId": "manual-local",
                "nftTable": "zap2_u1000_deadbeef_default",
                "nfqueueNum": 224,
                "queuedTcpPorts": ["80", "443-65535"],
                "queuedUdpPorts": ["80", "443-65535"],
                "capturePolicy": {"kind": "test"},
                "ownerUid": 1000,
                "ownerUidSource": "test",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    fake_binary = project / "fake-nfqws2-sleep"
    shutil.copyfile("/bin/sleep", fake_binary)
    fake_binary.chmod(0o755)
    proc = subprocess.Popen([str(fake_binary), "60"])
    try:
        identity = None
        for _ in range(20):
            identity = _capture_process_identity(proc.pid, fake_binary)
            if identity is not None:
                break
            time.sleep(0.01)
        assert identity is not None
        (sessions / "default.session.json").write_text(
            json.dumps(
                {
                    "schemaVersion": 2,
                    "stage": "test",
                    "marker": "zap2-runtime-session-v1",
                    "state": "running",
                    "profileId": "default",
                    "rootPath": str(project),
                    "pid": proc.pid,
                    "processIdentity": identity,
                    "binaryPath": str(fake_binary),
                    "planId": "runtime-default-manual-local-start-plan",
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        overview = gui_first_runtime_overview(project)
    finally:
        proc.terminate()
        proc.wait(timeout=5)

    assert overview.state == "mismatch"
    assert overview.primary_action == "restart"
    assert any("Запущена стратегия manual-local" in issue for issue in overview.issues)


def test_gui_first_overview_cli_is_read_only(capsys) -> None:
    assert main(["--gui-first-overview"]) == 0
    out = capsys.readouterr().out
    assert "GUI-first runtime overview" in out
    assert "read-only: yes" in out
    assert "executes now: no" in out


def test_gui_first_overview_table_rows_are_copyable_text(tmp_path: Path) -> None:
    project = _copy_project(tmp_path)
    overview = gui_first_runtime_overview(project)
    rows = overview.table_rows()
    table_text = overview.to_table_text()

    assert rows
    assert rows[0].as_tuple() == ("Профиль", "Workspace profile", "default", "info")
    assert any(row.section == "Стратегия" and row.field == "Выбрана в GUI" for row in rows)
    assert table_text.startswith("section\tfield\tvalue\tstatus")
    assert "\nСтратегия\tВыбрана в GUI\t" in table_text
    assert "PYTHONPATH=" not in table_text
    assert "sudo nft" not in table_text
