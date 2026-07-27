from __future__ import annotations

import json
import shutil
from pathlib import Path

from zap2_gui.app import main
from zap2_gui.adapters.har_discovery import analyze_har, domain_family, latest_har_summary
from zap2_gui.adapters.har_workbench import (
    build_har_workbench,
    har_group_plan_to_text,
    latest_har_workbench,
)

ROOT = Path(__file__).resolve().parents[1]


def _copy_project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    shutil.copytree(
        ROOT,
        project,
        ignore=shutil.ignore_patterns(".git", ".zap2", "__pycache__", "*.pyc", ".pytest_cache"),
    )
    return project


def _youtube_har() -> dict[str, object]:
    media_host = "rr8---sn-n8v7znlr.googlevideo.com"
    return {
        "log": {
            "entries": [
                {
                    "request": {
                        "method": "GET",
                        "url": "https://www.youtube.com/watch?v=private-video-id",
                        "headers": [{"name": "Cookie", "value": "private-cookie"}],
                    },
                    "response": {"status": 200, "statusText": "OK", "httpVersion": "HTTP/2", "headers": []},
                    "serverIPAddress": "203.0.113.10",
                },
                {
                    "request": {
                        "method": "GET",
                        "url": f"https://{media_host}/videoplayback?expire=secret&sig=private-signature",
                        "headers": [{"name": "Authorization", "value": "private-token"}],
                    },
                    "response": {"status": 0, "statusText": "NS_BINDING_ABORTED", "httpVersion": "HTTP/2", "headers": []},
                    "_error": "NS_BINDING_ABORTED private browser detail",
                },
                {
                    "request": {
                        "method": "GET",
                        "url": f"https://{media_host}/videoplayback?range=0-1000&token=must-not-survive",
                        "headers": [],
                    },
                    "response": {"status": 0, "statusText": "NS_BINDING_ABORTED", "httpVersion": "HTTP/2", "headers": []},
                    "_error": "NS_BINDING_ABORTED second private detail",
                },
                {
                    "request": {
                        "method": "GET",
                        "url": "https://assets.newservice.example/static/app.js?session=private",
                        "headers": [],
                    },
                    "response": {"status": 200, "statusText": "OK", "httpVersion": "HTTP/2", "headers": []},
                },
                {
                    "request": {
                        "method": "GET",
                        "url": "https://video-edge.example.net/chunk?id=private",
                        "headers": [],
                    },
                    "response": {"status": 0, "statusText": "", "httpVersion": "h3", "headers": []},
                    "_error": "net::ERR_QUIC_PROTOCOL_ERROR raw transport detail",
                },
            ]
        }
    }


def test_universal_har_keeps_any_resource_and_safe_error_codes(tmp_path: Path) -> None:
    project = _copy_project(tmp_path)
    har_path = tmp_path / "youtube.har"
    har_path.write_text(json.dumps(_youtube_har()), encoding="utf-8")

    summary = analyze_har(har_path, root=project)
    by_host = {item.host: item for item in summary.host_summaries}
    media = by_host["rr8---sn-n8v7znlr.googlevideo.com"]

    assert summary.unique_host_count == 4
    assert media.domain_family == "googlevideo.com"
    assert media.covered_by_default_hostlist is True
    assert media.browser_cancel_count == 2
    assert media.attention_level == "medium"
    assert "NS_BINDING_ABORTED" in media.error_codes
    assert "browser-cancelled" in media.issue_classes
    assert by_host["assets.newservice.example"].covered_by_any_hostlist is False
    assert domain_family("rr8---sn-n8v7znlr.googlevideo.com") == "googlevideo.com"

    payload = json.dumps(summary.to_dict(), ensure_ascii=False)
    for forbidden in (
        "private-cookie",
        "private-token",
        "private-signature",
        "must-not-survive",
        "private browser detail",
        "second private detail",
        "raw transport detail",
        "203.0.113.10",
    ):
        assert forbidden not in payload


def test_universal_workbench_groups_exact_hosts_by_family_l7_and_reason(tmp_path: Path) -> None:
    project = _copy_project(tmp_path)
    har_path = tmp_path / "youtube.har"
    har_path.write_text(json.dumps(_youtube_har()), encoding="utf-8")

    workbench = build_har_workbench(har_path, root=project)
    groups = {item.group_id: item for item in workbench.groups}

    cancelled = groups["har-googlevideo-com-tls-browser-cancelled"]
    assert cancelled.hosts == ("rr8---sn-n8v7znlr.googlevideo.com",)
    assert cancelled.covered_hosts == cancelled.hosts
    assert cancelled.suggested_hostlist_entries == ()
    assert "code:NS_BINDING_ABORTED" in cancelled.evidence
    assert cancelled.blockcheck_options().enable_https_tls13 is True

    uncovered = groups["har-newservice-example-tls-uncovered-observed"]
    assert uncovered.hosts == ("assets.newservice.example",)
    assert uncovered.suggested_hostlist_entries == ("assets.newservice.example",)

    quic = groups["har-example-net-quic-transport-failure"]
    assert quic.protocol == "udp"
    assert quic.blockcheck_options().enable_http3 is True

    saved = "\n".join(path.read_text(encoding="utf-8") for path in workbench.workbench_dir.rglob("*.json"))
    assert "NS_BINDING_ABORTED" in saved
    assert "private browser detail" not in saved
    assert "discord-voice-source-candidates" not in saved
    assert (workbench.workbench_dir / f"groups/{cancelled.group_id}/targets.txt").read_text(encoding="utf-8") == (
        "rr8---sn-n8v7znlr.googlevideo.com\n"
    )
    assert latest_har_summary(root=project) is not None
    assert latest_har_workbench(root=project) is not None
    assert "Blockcheck preflight" in har_group_plan_to_text(cancelled.group_id, root=project)
    assert "scope: any resource" in workbench.to_text()


def test_universal_har_cli_and_gui_source_are_not_discord_bound() -> None:
    assert main(["--har-plan"]) == 0
    app_text = (ROOT / "gui/zap2_gui/widgets/blockcheck_lab.py").read_text(encoding="utf-8")
    assert "build_har_workbench" in app_text
    assert "latest_har_workbench" in app_text
    assert "Импорт HAR для универсального workbench" in app_text
    assert "Discord Voice profiles" in app_text
