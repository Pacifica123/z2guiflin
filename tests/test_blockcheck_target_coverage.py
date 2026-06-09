from __future__ import annotations

import json
import shutil
from pathlib import Path

from zap2_gui.adapters.blockcheck_gui import (
    BLOCKCHECK_SCAN_ALL_TARGETS,
    BlockcheckOptions,
    blockcheck_coverage_manifest_path,
    blockcheck_coverage_to_text,
    build_blockcheck_command,
    export_blockcheck_available_strategies,
    write_blockcheck_last_log,
)
from zap2_gui.adapters.workspace_profiles import load_workspace_catalog, workspace_strategy_to_text
from zap2_gui.models.service_targets import SERVICE_TARGET_DISCORD_DESKTOP

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


def test_candidate_logs_update_discord_coverage_manifest(tmp_path: Path) -> None:
    project = _copy_project(tmp_path)

    _write_candidate(
        project,
        "discord.com",
        """
* script : standard/17-oob.sh
- curl_test_https_tls12 ipv4 discord.com : nfqws2 --in-range=-s1 --lua-desync=oob:urp=midsld
!!!!! AVAILABLE !!!!!
""",
    )

    manifest_path = blockcheck_coverage_manifest_path(project)
    data = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert data["serviceTargetPresetId"] == SERVICE_TARGET_DISCORD_DESKTOP
    assert data["scanMode"] == BLOCKCHECK_SCAN_ALL_TARGETS
    assert data["targets"]["discord.com"]["status"] == "available"
    assert data["targets"]["discord.com"]["availableStrategies"] == 1
    assert data["targets"]["stable.dl2.discordapp.net"]["status"] == "not-tested"
    assert Path(project / data["targets"]["discord.com"]["lastLog"]).is_file()

    text = blockcheck_coverage_to_text(project)
    assert "Blockcheck target coverage" in text
    assert "discord.com: available" in text
    assert "stable.dl2.discordapp.net: not-tested" in text


def test_export_uses_candidate_logs_and_embeds_per_target_coverage(tmp_path: Path) -> None:
    project = _copy_project(tmp_path)

    _write_candidate(
        project,
        "discord.com",
        """
* script : standard/17-oob.sh
- curl_test_https_tls12 ipv4 discord.com : nfqws2 --in-range=-s1 --lua-desync=oob:urp=midsld
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

    result = export_blockcheck_available_strategies(project)

    assert result.ok
    assert result.source_logs
    generated = result.generated[0]
    payload = json.loads(generated.path.read_text(encoding="utf-8"))
    coverage = payload["serviceTarget"]["coverage"]
    statuses = {item["target"]: item["status"] for item in coverage["targets"]}

    assert coverage["source"] == "blockcheck-candidate-coverage"
    assert statuses["discord.com"] == "available"
    assert statuses["stable.dl2.discordapp.net"] == "unavailable"
    assert statuses["gateway.discord.gg"] == "not-tested"
    assert generated.coverage_status == "available"

    catalog = load_workspace_catalog(project)
    strategy = catalog.strategy_by_id()[generated.strategy_id]
    assert "available=1" in strategy.service_target_coverage_label
    assert "unavailable=1" in strategy.service_target_coverage_label

    details = workspace_strategy_to_text(generated.strategy_id, project)
    assert "coverage:" in details
    assert "not a full-service guarantee" in details
