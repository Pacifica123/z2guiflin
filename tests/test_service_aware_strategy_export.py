from __future__ import annotations

import json
import shutil
from pathlib import Path

from zap2_gui.adapters.blockcheck_gui import (
    BlockcheckOptions,
    build_blockcheck_command,
    export_blockcheck_available_strategies,
)
from zap2_gui.adapters.workspace_profiles import load_workspace_catalog, workspace_strategy_to_text
from zap2_gui.models.service_targets import (
    SERVICE_TARGET_CUSTOM,
    SERVICE_TARGET_DISCORD_DESKTOP,
    SERVICE_TARGET_YOUTUBE_BASIC,
    infer_service_target_preset_id,
)

ROOT = Path(__file__).resolve().parents[1]


def _copy_project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    shutil.copytree(ROOT, project, ignore=shutil.ignore_patterns(".git", ".zap2", "__pycache__", "*.pyc", ".pytest_cache"))
    return project


def test_blockcheck_command_records_service_target_preset_in_plan_and_env() -> None:
    command = build_blockcheck_command(
        root=ROOT,
        options=BlockcheckOptions(
            domains="gateway.discord.gg",
            service_target_preset_id=SERVICE_TARGET_DISCORD_DESKTOP,
        ),
    )

    assert "service target preset: discord-desktop" in command.to_text()
    assert "Discord desktop non-voice" in command.to_text()
    assert any(item == "ZAP2_SERVICE_TARGET_PRESET=discord-desktop" for item in command.argv)


def test_service_target_inference_handles_sequential_candidate_logs() -> None:
    assert infer_service_target_preset_id("youtube.com www.youtube.com") == SERVICE_TARGET_YOUTUBE_BASIC
    assert infer_service_target_preset_id("gateway.discord.gg") == SERVICE_TARGET_DISCORD_DESKTOP
    assert infer_service_target_preset_id("example.com") == SERVICE_TARGET_CUSTOM


def test_blockcheck_export_tags_generated_strategy_with_service_target(tmp_path: Path) -> None:
    project = _copy_project(tmp_path)
    log_path = project / ".zap2" / "blockcheck" / "logs" / "latest-successful-blockcheck.txt"
    log_path.parent.mkdir(parents=True)
    log_path.write_text(
        """
Blockcheck GUI plan
domains: gateway.discord.gg
service target preset: discord-desktop (Discord desktop non-voice)

===== STDOUT =====
* script : standard/15-misc.sh
- curl_test_https_tls12 ipv4 gateway.discord.gg : nfqws2 --payload=tls_client_hello --lua-desync=tcpseg:pos=0,1
!!!!! AVAILABLE !!!!!
""".strip()
        + "\n",
        encoding="utf-8",
    )

    result = export_blockcheck_available_strategies(project)

    assert result.ok
    assert result.service_target_preset_id == SERVICE_TARGET_DISCORD_DESKTOP
    assert len(result.generated) == 1
    generated = result.generated[0]
    assert generated.service_target_preset_id == SERVICE_TARGET_DISCORD_DESKTOP
    assert generated.strategy_id.startswith("blockcheck-discord-desktop-gateway.discord.gg-")

    data = json.loads(generated.path.read_text(encoding="utf-8"))
    assert data["serviceTarget"]["presetId"] == SERVICE_TARGET_DISCORD_DESKTOP
    assert data["serviceTarget"]["title"] == "Discord desktop non-voice"
    assert data["serviceTarget"]["exportedCandidate"] == "gateway.discord.gg"
    assert data["sourcePreset"]["serviceTargetPresetId"] == SERVICE_TARGET_DISCORD_DESKTOP

    catalog = load_workspace_catalog(project)
    strategy = catalog.strategy_by_id()[generated.strategy_id]
    assert strategy.service_target_label == "Discord desktop non-voice (discord-desktop)"

    details = workspace_strategy_to_text(generated.strategy_id, project)
    assert "service target: Discord desktop non-voice (discord-desktop)" in details
