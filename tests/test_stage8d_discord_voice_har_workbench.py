from __future__ import annotations

import json
import shutil
from pathlib import Path

from zap2_gui.app import main
from zap2_gui.adapters.discord_har_workbench import (
    build_discord_har_workbench,
    discord_har_group_plan_to_text,
    latest_discord_har_workbench,
)
from zap2_gui.adapters.discord_voice_profiles import (
    DISCORD_VOICE_PRESET_IDS,
    discord_voice_profiles_to_text,
)
from zap2_gui.adapters.runtime_apply import create_runtime_apply_plan
from zap2_gui.adapters.workspace_profiles import load_strategy_catalog, select_workspace_strategy

ROOT = Path(__file__).resolve().parents[1]


def _copy_project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    shutil.copytree(
        ROOT,
        project,
        ignore=shutil.ignore_patterns(".git", ".zap2", "__pycache__", "*.pyc", ".pytest_cache"),
    )
    return project


def _sample_har() -> dict[str, object]:
    return {
        "log": {
            "entries": [
                {
                    "request": {
                        "method": "GET",
                        "url": "https://updates.discord.com/fail?token=must-not-survive",
                        "headers": [{"name": "Authorization", "value": "secret"}],
                    },
                    "response": {"status": 0, "httpVersion": "HTTP/2", "headers": []},
                    "_error": "net::ERR_CONNECTION_RESET raw-private-detail",
                },
                {
                    "request": {"method": "GET", "url": "wss://gateway.discord.gg/?v=9", "headers": []},
                    "response": {"status": 101, "httpVersion": "HTTP/1.1", "headers": []},
                    "_webSocketMessages": [{"data": "private-websocket-payload"}],
                },
                {
                    "request": {"method": "GET", "url": "https://cdn.discordapp.com/test", "headers": []},
                    "response": {"status": 403, "httpVersion": "h3", "headers": []},
                },
            ]
        }
    }


def test_har_workbench_groups_failures_and_writes_safe_inputs(tmp_path: Path) -> None:
    project = _copy_project(tmp_path)
    har_path = tmp_path / "discord.har"
    har_path.write_text(json.dumps(_sample_har()), encoding="utf-8")

    workbench = build_discord_har_workbench(har_path, root=project)
    groups = {item.group_id: item for item in workbench.groups}

    assert "har-tls-problems" in groups
    assert groups["har-tls-problems"].hosts == ("updates.discord.com",)
    assert "har-websocket-observed" in groups
    assert "har-quic-problems" in groups
    assert groups["har-quic-problems"].protocol == "udp"
    assert groups["har-quic-problems"].blockcheck_options().enable_http3 is True
    assert groups["discord-voice-source-candidates"].blockcheckable is False

    saved = "\n".join(path.read_text(encoding="utf-8") for path in workbench.workbench_dir.rglob("*.json"))
    assert "must-not-survive" not in saved
    assert "raw-private-detail" not in saved
    assert "private-websocket-payload" not in saved
    assert (workbench.workbench_dir / "groups/har-tls-problems/targets.txt").read_text(encoding="utf-8") == "updates.discord.com\n"
    assert latest_discord_har_workbench(root=project) is not None
    assert "executes Blockcheck now: no" in workbench.to_text()
    assert "Blockcheck preflight" in discord_har_group_plan_to_text("har-tls-problems", root=project)


def test_discord_voice_presets_are_registered_as_alternatives() -> None:
    catalog = load_strategy_catalog(ROOT)
    by_id = catalog.by_id()
    for preset_id in DISCORD_VOICE_PRESET_IDS:
        strategy = by_id[preset_id]
        assert strategy.is_plan_only is True
        assert strategy.capture_policy is not None
        assert strategy.capture_policy["tcpOutPorts"] == []
        assert strategy.capture_policy["profileHostlists"] == "omit"
        assert not any(arg.startswith("--wf-") or arg.startswith("--dpi-desync") for arg in strategy.runtime_args)
        assert "--payload=" in "\n".join(strategy.runtime_args)
    text = discord_voice_profiles_to_text(root=ROOT)
    assert "alternatives" not in text.lower()
    assert "это альтернативы" in text
    assert main(["--discord-voice-profiles"]) == 0


def test_discord_voice_capture_policy_drives_udp_only_nft_plan(tmp_path: Path) -> None:
    project = _copy_project(tmp_path)
    expected = {
        "discord-voice-upstream-conservative": ("50000-50099",),
        "discord-voice-flowseal-narrow": ("19294-19344", "50000-50100"),
        "discord-voice-guiwin-wide": ("443-65535",),
    }
    for preset_id, ports in expected.items():
        select_workspace_strategy(project, strategy_id=preset_id, profile_id="default")
        plan = create_runtime_apply_plan(project, action="apply", profile_id="default")
        assert plan.queued_tcp_ports == ()
        assert plan.queued_udp_ports == ports
        nft_text = "\n".join(" ".join(command.argv) for command in plan.commands)
        assert "udp dport" in nft_text
        assert "tcp dport" not in nft_text


def test_source_inventory_covers_all_imported_voice_families() -> None:
    inventory = json.loads((ROOT / "references/external/discord_voice_source_inventory.json").read_text(encoding="utf-8"))
    assert inventory["flowseal"]["matchedBatCount"] >= 10
    assert inventory["guiWindowsWinws2"]["strategyCount"] >= 50
    assert inventory["guiWindowsWinws2"]["matchingBuiltinPresetCount"] >= 50
    assert inventory["guiWindowsWinws1"]["strategyCount"] >= 10
    assert set(inventory["executablePresetIds"]) == set(DISCORD_VOICE_PRESET_IDS)
