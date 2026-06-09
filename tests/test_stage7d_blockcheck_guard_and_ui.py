from __future__ import annotations

from pathlib import Path

from zap2_gui.adapters.blockcheck_gui import (
    BLOCKCHECK_DEAD_TARGET_GUARD_OBSERVE_ONLY,
    BlockcheckOptions,
    build_blockcheck_command,
)

ROOT = Path(__file__).resolve().parents[1]


def test_dead_target_guard_can_be_observe_only_for_discord_ordered_phases() -> None:
    opts = BlockcheckOptions(
        domains="stable.dl2.discordapp.net",
        service_target_preset_id="discord-desktop",
        dead_target_guard=BLOCKCHECK_DEAD_TARGET_GUARD_OBSERVE_ONLY,
    )
    env = opts.to_env()
    command = build_blockcheck_command(root=ROOT, options=opts)

    assert env["ZAP2_DEAD_TARGET_GUARD"] == "observe-only"
    assert "ZAP2_DEAD_TARGET_GUARD=observe-only" in command.redacted_command_preview()
    assert "dead-target guard: observe-only" in command.to_text()


def test_blockcheck_lab_ui_exposes_guard_and_compact_action_groups() -> None:
    source = (ROOT / "gui" / "zap2_gui" / "widgets" / "blockcheck_lab.py").read_text(encoding="utf-8")

    assert "Auto-skip dead target" in source
    assert "actions_box = QtWidgets.QGroupBox(\"Actions\")" in source
    assert "secondary_buttons" in source
    assert "▶ Run" in source
    assert "■ Stop" in source
    assert "dead_guard_check.setChecked(False)" in source
    assert "prepared.command.options.dead_target_guard == BLOCKCHECK_DEAD_TARGET_GUARD_AUTO_STOP" in source


def test_flowseal_windows_reference_notes_document_non_executable_boundary() -> None:
    doc = (ROOT / "docs" / "DISCORD_FLOWSEAL_WINDOWS_REFERENCE.md").read_text(encoding="utf-8")

    assert "Flowseal" in doc
    assert "stable.dl2.discordapp.net" in doc
    assert "observe-only" in doc
    assert "не является исполняемым preset-ом" in doc
    assert "one-strategy custom list" in doc


def test_cli_discord_plan_defaults_to_observe_only_guard(capsys) -> None:
    from zap2_gui.app import main

    assert main(["--blockcheck-plan", "--blockcheck-target-preset", "discord-desktop"]) == 0
    out = capsys.readouterr().out

    assert "dead-target guard: observe-only" in out
    assert "ZAP2_DEAD_TARGET_GUARD=observe-only" in out


def test_cli_can_force_auto_stop_guard(capsys) -> None:
    from zap2_gui.app import main

    assert main([
        "--blockcheck-plan",
        "--blockcheck-target-preset",
        "discord-desktop",
        "--blockcheck-dead-target-guard",
        "auto-stop",
    ]) == 0
    out = capsys.readouterr().out

    assert "dead-target guard: auto-stop" in out
