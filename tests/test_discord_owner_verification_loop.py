from __future__ import annotations

import shutil
from pathlib import Path

from zap2_gui.adapters.discord_verification import (
    discord_non_voice_report_path,
    discord_non_voice_report_template,
    discord_non_voice_verification_plan_to_text,
    write_discord_non_voice_report_template,
)
from zap2_gui.app import main
from zap2_gui.models.service_targets import DISCORD_DESKTOP_TARGETS, SERVICE_TARGET_DISCORD_DESKTOP

ROOT = Path(__file__).resolve().parents[1]


def _copy_project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    shutil.copytree(ROOT, project, ignore=shutil.ignore_patterns(".git", ".zap2", "__pycache__", "*.pyc", ".pytest_cache"))
    return project


def test_discord_verification_plan_is_owner_facing_and_non_executing() -> None:
    text = discord_non_voice_verification_plan_to_text(ROOT)

    assert "Discord non-voice owner verification loop" in text
    assert f"service target preset: {SERVICE_TARGET_DISCORD_DESKTOP}" in text
    assert "executes now: no" in text
    assert "mutates firewall/services now: no" in text
    assert "PYTHONPATH=gui python -m zap2_gui.app --blockcheck-run --blockcheck-target-preset discord-desktop" in text
    assert "--blockcheck-export-strategies" in text
    assert "--select-strategy <blockcheck-discord-desktop-...>" in text
    assert "--default-start-plan" in text
    assert "gateway.discord.gg" in text
    assert "cdn.discordapp.com" in text
    assert "Voice channels" in text
    assert "одновременная работа YouTube и Discord" in text

    for target in DISCORD_DESKTOP_TARGETS:
        assert target in text


def test_discord_report_template_records_success_and_failure_buckets() -> None:
    text = discord_non_voice_report_template(created_at="2026-06-09T13:30:00Z")

    assert "Service target preset: `discord-desktop`" in text
    assert "Voice/UDP: excluded from this report." in text
    assert "- [ ] Discord desktop открывается" in text
    assert "- [ ] Gateway работает" in text
    assert "- [ ] CDN/media работают" in text
    assert "blockcheck-no-available" in text
    assert "gateway-only-failure" in text
    assert "cdn-media-failure" in text
    assert "regression-youtube" in text
    assert "Non-voice не подтверждён; voice/UDP пока не начинать" in text


def test_discord_report_template_is_written_under_zap2_without_overwrite(tmp_path: Path) -> None:
    project = _copy_project(tmp_path)

    path = write_discord_non_voice_report_template(project)
    assert path == discord_non_voice_report_path(project)
    assert path.name == "discord-non-voice-owner-check.md"
    assert path.read_text(encoding="utf-8").startswith("# Discord desktop non-voice owner verification report")

    path.write_text("owner notes stay\n", encoding="utf-8")
    assert write_discord_non_voice_report_template(project) == path
    assert path.read_text(encoding="utf-8") == "owner notes stay\n"


def test_discord_verification_cli_commands(capsys) -> None:
    assert main(["--discord-verification-plan"]) == 0
    plan_output = capsys.readouterr().out
    assert "Discord non-voice owner verification loop" in plan_output
    assert "discord-desktop" in plan_output


def test_blockcheck_lab_widget_exposes_discord_owner_checklist() -> None:
    source = (ROOT / "gui" / "zap2_gui" / "widgets" / "blockcheck_lab.py").read_text(encoding="utf-8")

    assert "Discord checklist" in source
    assert "discord_non_voice_verification_plan_to_text" in source
