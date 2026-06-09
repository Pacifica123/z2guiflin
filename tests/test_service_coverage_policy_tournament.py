from __future__ import annotations

import json
import shutil
from pathlib import Path

from zap2_gui.adapters.blockcheck_gui import (
    BLOCKCHECK_SCAN_ALL_TARGETS,
    BlockcheckOptions,
    blockcheck_service_policy_to_text,
    blockcheck_tournament_to_text,
    build_blockcheck_command,
    write_blockcheck_last_log,
)
from zap2_gui.app import main
from zap2_gui.models.service_targets import (
    SERVICE_COVERAGE_ANY_TARGET_AVAILABLE,
    SERVICE_COVERAGE_ORDERED_TARGET_CHAIN,
    SERVICE_TARGET_DISCORD_DESKTOP,
    SERVICE_TARGET_YOUTUBE_BASIC,
    get_service_target_preset,
    service_target_ordered_targets,
    service_target_recommended_scan_mode,
)

ROOT = Path(__file__).resolve().parents[1]


def _copy_project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    shutil.copytree(ROOT, project, ignore=shutil.ignore_patterns(".git", ".zap2", "__pycache__", "*.pyc", ".pytest_cache"))
    return project


def _write_candidate(project: Path, target: str, stdout: str) -> None:
    command = build_blockcheck_command(
        root=project,
        options=BlockcheckOptions(
            domains=target,
            service_target_preset_id=SERVICE_TARGET_DISCORD_DESKTOP,
            scan_mode=BLOCKCHECK_SCAN_ALL_TARGETS,
        ),
    )
    write_blockcheck_last_log(command, stdout, "", footer=f"candidate: {target}")


def test_service_coverage_policy_distinguishes_youtube_and_discord() -> None:
    youtube = get_service_target_preset(SERVICE_TARGET_YOUTUBE_BASIC)
    discord = get_service_target_preset(SERVICE_TARGET_DISCORD_DESKTOP)

    assert youtube.policy.mode == SERVICE_COVERAGE_ANY_TARGET_AVAILABLE
    assert youtube.policy.order_mode == "order-not-important"
    assert service_target_recommended_scan_mode(SERVICE_TARGET_YOUTUBE_BASIC) == "stop-after-first-available"

    assert discord.policy.mode == SERVICE_COVERAGE_ORDERED_TARGET_CHAIN
    assert discord.policy.order_mode == "order-important"
    assert service_target_recommended_scan_mode(SERVICE_TARGET_DISCORD_DESKTOP) == "scan-all-targets"
    assert service_target_ordered_targets(SERVICE_TARGET_DISCORD_DESKTOP)[:3] == (
        "updates.discord.com",
        "stable.dl2.discordapp.net",
        "discord.com",
    )


def test_service_policy_text_is_read_only_and_owner_facing() -> None:
    text = blockcheck_service_policy_to_text(SERVICE_TARGET_DISCORD_DESKTOP)

    assert "Service target coverage policy" in text
    assert "coverage mode: ordered-target-chain" in text
    assert "1. updates.discord.com [updater]" in text
    assert "read-only: yes" in text
    assert "mutates services/firewall now: no" in text


def test_tournament_scores_ordered_prefix_from_coverage_manifest(tmp_path: Path) -> None:
    project = _copy_project(tmp_path)

    _write_candidate(
        project,
        "updates.discord.com",
        """
* script : standard/17-oob.sh
- curl_test_https_tls12 ipv4 updates.discord.com : nfqws2 --in-range=-s1 --lua-desync=oob:urp=midsld
!!!!! AVAILABLE !!!!!
""",
    )
    _write_candidate(
        project,
        "stable.dl2.discordapp.net",
        """
* script : standard/15-misc.sh
- curl_test_https_tls12 ipv4 stable.dl2.discordapp.net : nfqws2 --payload=tls_client_hello
curl: (28) Connection timed out after 3002 milliseconds
UNAVAILABLE code=28
""",
    )
    manifest = project / ".zap2" / "blockcheck" / "logs" / "candidates" / "coverage-manifest.json"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert data["coveragePolicy"] == "ordered-target-chain"
    assert data["coverageOrderMode"] == "order-important"

    text = blockcheck_tournament_to_text(project, preset_id=SERVICE_TARGET_DISCORD_DESKTOP)

    assert "Blockcheck service coverage tournament" in text
    assert "score: 1/9 available" in text
    assert "ordered prefix: 1/9" in text
    assert "first blocker: stable.dl2.discordapp.net (unavailable" in text
    assert "full coverage: no" in text
    assert "Stage 7a does not yet prove one nfqws command across every domain" in text


def test_blockcheck_cli_exposes_policy_and_tournament(capsys) -> None:
    assert main(["--blockcheck-service-policy", "--blockcheck-target-preset", "discord-desktop"]) == 0
    out = capsys.readouterr().out
    assert "coverage mode: ordered-target-chain" in out

    assert main(["--blockcheck-tournament", "--blockcheck-target-preset", "discord-desktop"]) == 0
    out = capsys.readouterr().out
    assert "Blockcheck service coverage tournament" in out
    assert "preset: discord-desktop" in out
