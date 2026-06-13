from __future__ import annotations

import json
import shutil
from pathlib import Path

from zap2_gui.adapters.discord_observation_matrix import (
    MATRIX_PLAN_ROWS,
    collect_observation_matrix,
    discord_observation_matrix_plan_to_text,
)
from zap2_gui.app import main

ROOT = Path(__file__).resolve().parents[1]


def _copy_project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    shutil.copytree(ROOT, project, ignore=shutil.ignore_patterns(".git", ".zap2", "__pycache__", "*.pyc", ".pytest_cache"))
    return project


def _write_guided_report(project: Path, *, strategy_id: str, verdict: str = "V9_ESTAB_WITH_SENDQ", out_delta: int = 8) -> Path:
    reports = project / ".zap2" / "runtime" / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    safe = strategy_id.replace("/", "-")
    path = reports / f"discord-pretls-guided-probe-default-20260613-{safe}.json"
    payload = {
        "schemaVersion": 1,
        "stage": "v0.4-alpha_stage7n3",
        "kind": "discord-pretls-guided-probe-report",
        "createdAt": "2026-06-13T10:00:00Z",
        "profileId": "default",
        "selectedStrategyId": strategy_id,
        "activeStrategyId": strategy_id,
        "verdict": verdict,
        "nextBranch": "matrix test next branch",
        "counterDeltas": {
            "tcpOutPackets": {"before": 0, "after": out_delta, "delta": out_delta},
            "tcpInSynAckPackets": {"before": 0, "after": 1, "delta": 1},
        },
        "endpointSummary": {
            "states": {"ESTAB": 3},
            "primaryEndpoint": "TCP 162.159.137.232:443 state=ESTAB recvq=0 sendq=268 pid=16790",
        },
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _write_endpoint_snapshot(project: Path) -> Path:
    out = project / ".zap2" / "discord-discovery"
    out.mkdir(parents=True, exist_ok=True)
    path = out / "endpoint-snapshot-20260613T100000Z.json"
    payload = {
        "schemaVersion": 2,
        "createdAt": "2026-06-13T10:00:00Z",
        "seconds": 30,
        "samples": 30,
        "processLines": ["16790 /home/noir/.config/discord/Discord"],
        "dnsMap": [],
        "warnings": [],
        "observations": [
            {
                "proto": "tcp",
                "local": "192.168.0.100:60540",
                "peer": "162.159.137.232:443",
                "peerHost": "162.159.137.232",
                "peerPort": "443",
                "state": "ESTAB",
                "recvQ": "0",
                "sendQ": "268",
                "timer": "on,35sec,10",
                "process": "users:((\"Discord\",pid=16790,fd=118))",
                "pid": "16790",
                "processName": "Discord",
                "sightings": 5,
                "matchedHosts": ["updates.discord.com"],
            }
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def test_stage7o2_plan_lists_expected_rows() -> None:
    text = discord_observation_matrix_plan_to_text(ROOT)
    labels = [row.label for row in MATRIX_PLAN_ROWS]

    assert "Discord observation matrix plan" in text
    assert "no zapret baseline" in text
    assert "diagnostic pktdebug" in text
    assert "current v2 strategy" in text
    assert "kartavkun-like multisplit" in text
    assert "fake_tls_auto-like" in text
    assert "simple_fake-like" in text
    assert len(labels) == 6


def test_stage7o2_report_aggregates_guided_reports_and_baseline(tmp_path: Path) -> None:
    project = _copy_project(tmp_path)
    _write_endpoint_snapshot(project)
    _write_guided_report(project, strategy_id="community-discord-pretls-diagnostic-pktdebug")
    _write_guided_report(project, strategy_id="reference-linux-general-multisplit-like", verdict="V8_TCP_ESTABLISHED", out_delta=4)

    report = collect_observation_matrix(project)
    rows = {row.row_id: row for row in report.rows}

    assert rows["baseline-no-zapret"].status == "available"
    assert rows["diagnostic-pktdebug"].status == "available"
    assert rows["diagnostic-pktdebug"].tcp_out_delta == 8
    assert rows["reference-kartavkun-multisplit"].verdict == "V8_TCP_ESTABLISHED"
    assert rows["reference-fake-tls-auto"].status == "missing"
    assert report.report_json_path.exists()
    assert report.report_md_path.exists()
    payload = json.loads(report.report_json_path.read_text(encoding="utf-8"))
    assert payload["stage"] == "v0.4-alpha_stage7o2"
    assert len(payload["rows"]) == 6


def test_stage7o2_cli_exposes_plan_and_report(capsys) -> None:
    assert main(["--discord-observation-matrix-plan"]) == 0
    out = capsys.readouterr().out
    assert "Discord observation matrix plan" in out
    assert "current v2 strategy" in out

    assert main(["--discord-observation-matrix-report"]) == 0
    out = capsys.readouterr().out
    assert "Discord observation matrix report" in out
    assert "report json:" in out


def test_stage7o2_docs_keep_matrix_non_executable() -> None:
    docs = (ROOT / "docs" / "DISCORD_OBSERVATION_MATRIX.md").read_text(encoding="utf-8")
    snippet = (ROOT / "references" / "external" / "snippets" / "stage7o2-observation-matrix-plan.txt").read_text(encoding="utf-8")

    assert "does not add a new bypass strategy" in docs
    assert "does not execute external scripts" in snippet
    assert "no zapret baseline" in snippet
