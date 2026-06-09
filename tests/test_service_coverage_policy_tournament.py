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
        "stable.dl2.discordapp.net",
        "updates.discord.com",
        "discord.com",
    )
    assert get_service_target_preset(SERVICE_TARGET_DISCORD_DESKTOP).phases[0].targets == (
        "stable.dl2.discordapp.net",
        "updates.discord.com",
    )


def test_service_policy_text_is_read_only_and_owner_facing() -> None:
    text = blockcheck_service_policy_to_text(SERVICE_TARGET_DISCORD_DESKTOP)

    assert "Service target coverage policy" in text
    assert "coverage mode: ordered-target-chain" in text
    assert "phase order: phases use AND; targets inside a phase use OR" in text
    assert "1. updater (Updater/bootstrap; required): stable.dl2.discordapp.net, updates.discord.com" in text
    assert "1. stable.dl2.discordapp.net [updater]" in text
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
    assert "phase score: 1/5 required phases passed" in text
    assert "phase prefix: 1/5" in text
    assert "first blocker phase: app-api (not-tested" in text
    assert "full coverage: no" in text
    assert "phase logic: phases use AND; targets inside the same phase use OR" in text
    assert "one strategy at a time" in text


def test_blockcheck_cli_exposes_policy_and_tournament(capsys) -> None:
    assert main(["--blockcheck-service-policy", "--blockcheck-target-preset", "discord-desktop"]) == 0
    out = capsys.readouterr().out
    assert "coverage mode: ordered-target-chain" in out

    assert main(["--blockcheck-tournament", "--blockcheck-target-preset", "discord-desktop"]) == 0
    out = capsys.readouterr().out
    assert "Blockcheck service coverage tournament" in out
    assert "preset: discord-desktop" in out


def test_one_strategy_validation_plan_writes_single_custom_lists(tmp_path: Path) -> None:
    project = _copy_project(tmp_path)

    _write_candidate(
        project,
        "stable.dl2.discordapp.net",
        """
* script : standard/25-fake.sh
- curl_test_https_tls12 ipv4 stable.dl2.discordapp.net : nfqws2 --payload=tls_client_hello --lua-desync=multidisorder:pos=2
!!!!! AVAILABLE !!!!!
""",
    )
    result = __import__("zap2_gui.adapters.blockcheck_gui", fromlist=["export_blockcheck_available_strategies"]).export_blockcheck_available_strategies(project, max_strategies=1)
    strategy_id = result.generated[0].strategy_id

    from zap2_gui.adapters.blockcheck_gui import blockcheck_strategy_validation_plan_to_text, write_blockcheck_strategy_validation_lists

    lists = write_blockcheck_strategy_validation_lists(project, strategy_id=strategy_id)
    tls12 = lists.root_dir / "list_https_tls12.txt"
    tls13 = lists.root_dir / "list_https_tls13.txt"

    assert tls12.read_text(encoding="utf-8").strip() == "--payload=tls_client_hello --lua-desync=multidisorder:pos=2"
    assert tls13.read_text(encoding="utf-8").strip() == "--payload=tls_client_hello --lua-desync=multidisorder:pos=2"
    assert "--filter-tcp" not in tls12.read_text(encoding="utf-8")
    assert "--lua-init" not in tls12.read_text(encoding="utf-8")

    text = blockcheck_strategy_validation_plan_to_text(project, strategy_id=strategy_id, target="discord.com")
    assert "Blockcheck one-strategy validation plan" in text
    assert "strategy: " + strategy_id in text
    assert "target: discord.com" in text
    assert "LIST_HTTPS_TLS12=" in text
    assert "TEST=custom" in text or "custom list root" in text
    assert "executes now: no" in text


def test_ordered_tournament_gui_runner_is_phase_gated() -> None:
    source = (ROOT / "gui" / "zap2_gui" / "widgets" / "blockcheck_lab.py").read_text(encoding="utf-8")

    assert "Phase-gated Blockcheck tournament run" in source
    assert "do not advance to later phases until the current phase has an AVAILABLE alternative" in source
    assert "Tournament phase blocked: no AVAILABLE alternative in required phase" in source
    assert "phase-alternative-available" in source
    assert "service_target_phase_chain" in source
