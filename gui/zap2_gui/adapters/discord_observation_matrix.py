"""Discord observation matrix helper for Stage 7o2.

Stage 7o0/7o1 added an external-reference lane.  Stage 7o2 does not pick a
winner and does not run strategies.  It gives the owner one matrix-shaped plan
and one read-only aggregator so baseline, diagnostic and external-inspired
candidate runs can be compared without turning every new archive into another
ad-hoc Discord preset.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .discord_endpoint_discovery import DiscordEndpointSnapshot, latest_discord_endpoint_snapshot, run_discord_endpoint_watch
from .runtime_default import execute_default_workflow, prepare_default_workflow_plan
from .runtime_default_build import execute_default_build, prepare_default_build_plan
from .runtime_nft_state import runtime_nft_state_snapshot
from .runtime_state import confirm_runtime_plan
from .runtime_state import ensure_runtime_store
from .workspace_profiles import load_strategy_catalog, load_workspace_catalog, select_workspace_strategy
from ..project_paths import discover_layout


MATRIX_STAGE = "v0.4-alpha_stage7o2"
MATRIX_RUNNER_STAGE = "v0.4-alpha_stage7o2d"
DEFAULT_MATRIX_ROW_SECONDS = 45

Emit = Callable[[str], None]
InputFunc = Callable[[str], str]
EndpointWatchRunner = Callable[..., DiscordEndpointSnapshot]


@dataclass(frozen=True)
class ObservationMatrixPlanRow:
    row_id: str
    label: str
    strategy_id: str | None
    mode: str
    purpose: str
    run_command: str
    expected_evidence: str

    def to_dict(self) -> dict[str, str | None]:
        return {
            "rowId": self.row_id,
            "label": self.label,
            "strategyId": self.strategy_id,
            "mode": self.mode,
            "purpose": self.purpose,
            "runCommand": self.run_command,
            "expectedEvidence": self.expected_evidence,
        }


@dataclass(frozen=True)
class ObservationMatrixRow:
    row_id: str
    label: str
    strategy_id: str | None
    mode: str
    status: str
    evidence_path: str
    verdict: str
    tcp_out_delta: int | None
    tcp_in_synack_delta: int | None
    endpoint_states: dict[str, int]
    primary_endpoint: str
    next_branch: str
    notes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "rowId": self.row_id,
            "label": self.label,
            "strategyId": self.strategy_id,
            "mode": self.mode,
            "status": self.status,
            "evidencePath": self.evidence_path,
            "verdict": self.verdict,
            "tcpOutDelta": self.tcp_out_delta,
            "tcpInSynAckDelta": self.tcp_in_synack_delta,
            "endpointStates": dict(self.endpoint_states),
            "primaryEndpoint": self.primary_endpoint,
            "nextBranch": self.next_branch,
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class ObservationMatrixReport:
    created_at: str
    profile_id: str
    rows: tuple[ObservationMatrixRow, ...]
    report_json_path: Path
    report_md_path: Path

    def to_payload(self) -> dict[str, Any]:
        return {
            "schemaVersion": 1,
            "stage": MATRIX_STAGE,
            "kind": "discord-observation-matrix-report",
            "createdAt": self.created_at,
            "profileId": self.profile_id,
            "rows": [row.to_dict() for row in self.rows],
            "execution": {
                "readOnly": True,
                "startsRuntimeNow": False,
                "appliesFirewallNow": False,
                "executesDiscordNow": False,
                "writesReportFiles": True,
            },
        }

    def to_markdown(self) -> str:
        lines = [
            "# Discord observation matrix report",
            "",
            f"createdAt: `{self.created_at}`",
            f"profile: `{self.profile_id}`",
            f"stage: `{MATRIX_STAGE}`",
            "",
            "This report aggregates existing guided probe reports and the latest no-zapret endpoint snapshot. It does not run strategies and does not mutate nftables/services.",
            "",
            "| row | mode | status | verdict | tcp-out Δ | synack Δ | endpoint states | primary endpoint |",
            "|---|---|---|---|---:|---:|---|---|",
        ]
        for row in self.rows:
            states = ", ".join(f"{key}={value}" for key, value in sorted(row.endpoint_states.items())) or "нет"
            lines.append(
                f"| `{row.label}` | `{row.mode}` | `{row.status}` | `{row.verdict or 'n/a'}` | "
                f"{row.tcp_out_delta if row.tcp_out_delta is not None else 'n/a'} | "
                f"{row.tcp_in_synack_delta if row.tcp_in_synack_delta is not None else 'n/a'} | "
                f"{states} | `{row.primary_endpoint or 'нет'}` |"
            )
        lines.extend(["", "## Row details", ""])
        for row in self.rows:
            lines.extend([
                f"### {row.label}",
                "",
                f"rowId: `{row.row_id}`",
                f"strategy: `{row.strategy_id or 'none'}`",
                f"mode: `{row.mode}`",
                f"status: `{row.status}`",
                f"evidence: `{row.evidence_path or 'missing'}`",
                f"verdict: `{row.verdict or 'n/a'}`",
                f"next branch: {row.next_branch or 'n/a'}",
                "",
                "notes:",
            ])
            lines.extend(f"- {note}" for note in row.notes)
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"

    def to_text(self) -> str:
        lines = [
            "Discord observation matrix report",
            f"profile: {self.profile_id}",
            f"created at: {self.created_at}",
            "read-only: yes",
            "starts runtime now: no",
            "applies firewall/services now: no",
            "executes Discord now: no",
            "",
            "rows:",
        ]
        for row in self.rows:
            states = ", ".join(f"{key}={value}" for key, value in sorted(row.endpoint_states.items())) or "нет"
            lines.extend([
                f"  - {row.label}",
                f"    strategy: {row.strategy_id or 'none'}",
                f"    mode: {row.mode}; status: {row.status}",
                f"    verdict: {row.verdict or 'n/a'}",
                f"    tcp-out delta: {row.tcp_out_delta if row.tcp_out_delta is not None else 'n/a'}; synack delta: {row.tcp_in_synack_delta if row.tcp_in_synack_delta is not None else 'n/a'}",
                f"    endpoint states: {states}",
                f"    primary endpoint: {row.primary_endpoint or 'нет'}",
                f"    evidence: {row.evidence_path or 'missing'}",
                f"    next branch: {row.next_branch or 'n/a'}",
            ])
        lines.extend([
            "",
            f"report json: {self.report_json_path}",
            f"report md: {self.report_md_path}",
            "",
            "interpretation:",
            "  - Missing rows mean the corresponding guided run has not been performed yet.",
            "  - Compare verdicts and endpoint states before promoting any reference candidate into a real Discord strategy.",
        ])
        return "\n".join(lines)


MATRIX_PLAN_ROWS: tuple[ObservationMatrixPlanRow, ...] = (
    ObservationMatrixPlanRow(
        row_id="baseline-no-zapret",
        label="no zapret baseline",
        strategy_id=None,
        mode="endpoint-watch-only",
        purpose="Observe Discord without Zap2 runtime so SYN-SENT/ESTAB/updater behavior is not blamed on nfqws2.",
        run_command="PYTHONPATH=gui python -m zap2_gui.app --discord-observation-matrix-run-row baseline-no-zapret",
        expected_evidence=".zap2/discord-discovery/endpoint-snapshot-*.json",
    ),
    ObservationMatrixPlanRow(
        row_id="diagnostic-pktdebug",
        label="diagnostic pktdebug",
        strategy_id="community-discord-pretls-diagnostic-pktdebug",
        mode="guided-probe",
        purpose="Validate the observability funnel: nft counter, qnum, live nfqws2 and endpoint correlation.",
        run_command="PYTHONPATH=gui python -m zap2_gui.app --discord-observation-matrix-run-row diagnostic-pktdebug",
        expected_evidence="discord-pretls-guided-probe-*.json with strategy community-discord-pretls-diagnostic-pktdebug",
    ),
    ObservationMatrixPlanRow(
        row_id="current-v2-syndata",
        label="current v2 strategy",
        strategy_id="community-discord-syndata-edge-flow-v2",
        mode="guided-probe",
        purpose="Re-test the strongest current Zap2 Discord early-flow candidate under the same observation harness.",
        run_command="PYTHONPATH=gui python -m zap2_gui.app --discord-observation-matrix-run-row current-v2-syndata",
        expected_evidence="discord-pretls-guided-probe-*.json with strategy community-discord-syndata-edge-flow-v2",
    ),
    ObservationMatrixPlanRow(
        row_id="reference-kartavkun-multisplit",
        label="kartavkun-like multisplit",
        strategy_id="reference-linux-general-multisplit-like",
        mode="guided-probe",
        purpose="Check whether a broad Linux reference multisplit-like candidate changes updater behavior.",
        run_command="PYTHONPATH=gui python -m zap2_gui.app --discord-observation-matrix-run-row reference-kartavkun-multisplit",
        expected_evidence="discord-pretls-guided-probe-*.json with strategy reference-linux-general-multisplit-like",
    ),
    ObservationMatrixPlanRow(
        row_id="reference-fake-tls-auto",
        label="fake_tls_auto-like",
        strategy_id="reference-zapret2-generic-tls-fake",
        mode="guided-probe",
        purpose="Check a zapret2-style generic TLS fake candidate inspired by working reference packs.",
        run_command="PYTHONPATH=gui python -m zap2_gui.app --discord-observation-matrix-run-row reference-fake-tls-auto",
        expected_evidence="discord-pretls-guided-probe-*.json with strategy reference-zapret2-generic-tls-fake",
    ),
    ObservationMatrixPlanRow(
        row_id="reference-simple-fake",
        label="simple_fake-like",
        strategy_id="reference-flowseal-simple-fake-like",
        mode="guided-probe",
        purpose="Check a broad Flowseal/simple-fake inspired candidate without importing external scripts.",
        run_command="PYTHONPATH=gui python -m zap2_gui.app --discord-observation-matrix-run-row reference-simple-fake",
        expected_evidence="discord-pretls-guided-probe-*.json with strategy reference-flowseal-simple-fake-like",
    ),
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _reports_dir(root: Path) -> Path:
    return ensure_runtime_store(root).root / ".zap2" / "runtime" / "reports"


def _report_paths(root: Path, created_at: str) -> tuple[Path, Path]:
    safe_stamp = re.sub(r"[^0-9TZ]", "", created_at).replace("T", "-").replace("Z", "") or "unknown"
    reports_dir = _reports_dir(root)
    reports_dir.mkdir(parents=True, exist_ok=True)
    base = reports_dir / f"discord-observation-matrix-{safe_stamp}"
    return base.with_suffix(".json"), base.with_suffix(".md")


def _safe_read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _latest_guided_reports_by_strategy(root: Path, profile_id: str) -> dict[str, tuple[Path, dict[str, Any]]]:
    result: dict[str, tuple[Path, dict[str, Any]]] = {}
    reports_dir = _reports_dir(root)
    if not reports_dir.exists():
        return result
    for path in sorted(reports_dir.glob("discord-pretls-guided-probe-*.json")):
        payload = _safe_read_json(path)
        if payload.get("kind") != "discord-pretls-guided-probe-report":
            continue
        if str(payload.get("profileId", "default")) != profile_id:
            continue
        strategy_id = str(payload.get("activeStrategyId") or payload.get("selectedStrategyId") or "")
        if not strategy_id:
            continue
        created = str(payload.get("createdAt", ""))
        old = result.get(strategy_id)
        if old is None or created >= str(old[1].get("createdAt", "")):
            result[strategy_id] = (path, payload)
    return result


def _delta(payload: dict[str, Any], key: str) -> int | None:
    value = payload.get("counterDeltas", {}).get(key, {})
    if not isinstance(value, dict):
        return None
    delta = value.get("delta")
    try:
        return None if delta is None else int(delta)
    except (TypeError, ValueError):
        return None


def _endpoint_states_from_payload(payload: dict[str, Any]) -> dict[str, int]:
    summary = payload.get("endpointSummary")
    if not isinstance(summary, dict):
        return {}
    states = summary.get("states", {})
    if not isinstance(states, dict):
        return {}
    cleaned: dict[str, int] = {}
    for key, value in states.items():
        try:
            cleaned[str(key)] = int(value)
        except (TypeError, ValueError):
            continue
    return cleaned


def _row_from_guided(row: ObservationMatrixPlanRow, path: Path | None, payload: dict[str, Any] | None) -> ObservationMatrixRow:
    if path is None or payload is None:
        return ObservationMatrixRow(
            row_id=row.row_id,
            label=row.label,
            strategy_id=row.strategy_id,
            mode=row.mode,
            status="missing",
            evidence_path="",
            verdict="",
            tcp_out_delta=None,
            tcp_in_synack_delta=None,
            endpoint_states={},
            primary_endpoint="",
            next_branch="Run the row and regenerate the observation matrix report.",
            notes=("No guided probe report found for this strategy.",),
        )
    summary = payload.get("endpointSummary") if isinstance(payload.get("endpointSummary"), dict) else {}
    return ObservationMatrixRow(
        row_id=row.row_id,
        label=row.label,
        strategy_id=row.strategy_id,
        mode=row.mode,
        status="available",
        evidence_path=str(path),
        verdict=str(payload.get("verdict", "")),
        tcp_out_delta=_delta(payload, "tcpOutPackets"),
        tcp_in_synack_delta=_delta(payload, "tcpInSynAckPackets"),
        endpoint_states=_endpoint_states_from_payload(payload),
        primary_endpoint=str(summary.get("primaryEndpoint", "")) if isinstance(summary, dict) else "",
        next_branch=str(payload.get("nextBranch", "")),
        notes=(f"guided report created at {payload.get('createdAt', 'unknown')}",),
    )


def _row_from_baseline(root: Path, row: ObservationMatrixPlanRow) -> ObservationMatrixRow:
    snapshot = latest_discord_endpoint_snapshot(root)
    if snapshot is None:
        return ObservationMatrixRow(
            row_id=row.row_id,
            label=row.label,
            strategy_id=None,
            mode=row.mode,
            status="missing",
            evidence_path="",
            verdict="",
            tcp_out_delta=None,
            tcp_in_synack_delta=None,
            endpoint_states={},
            primary_endpoint="",
            next_branch="Stop Zap2 runtime, run endpoint-watch while launching Discord, then regenerate the matrix.",
            notes=("No endpoint snapshot found for the no-zapret baseline row.",),
        )
    states: dict[str, int] = {}
    primary = ""
    best = -1
    for item in snapshot.observations:
        count = max(item.sightings, 1)
        state = item.state or "?"
        states[state] = states.get(state, 0) + count
        if count > best:
            best = count
            primary = f"{item.proto.upper()} {item.peer_host}:{item.peer_port or '?'} state={item.state or '?'} recvq={item.recv_q or '?'} sendq={item.send_q or '?'} pid={item.pid or '?'}"
    return ObservationMatrixRow(
        row_id=row.row_id,
        label=row.label,
        strategy_id=None,
        mode=row.mode,
        status="available",
        evidence_path=str(snapshot.output_path or ""),
        verdict="BASELINE_ENDPOINT_SNAPSHOT",
        tcp_out_delta=None,
        tcp_in_synack_delta=None,
        endpoint_states=states,
        primary_endpoint=primary,
        next_branch="Use this baseline only as a comparison point; it is not a Zap2 strategy verdict.",
        notes=(f"endpoint snapshot created at {snapshot.created_at}",),
    )


def collect_observation_matrix(root: Path | None = None, profile_id: str = "default") -> ObservationMatrixReport:
    layout = discover_layout(root)
    created_at = _utc_now()
    report_json, report_md = _report_paths(layout.root, created_at)
    latest = _latest_guided_reports_by_strategy(layout.root, profile_id)
    rows: list[ObservationMatrixRow] = []
    for plan_row in MATRIX_PLAN_ROWS:
        if plan_row.strategy_id is None:
            rows.append(_row_from_baseline(layout.root, plan_row))
        else:
            found = latest.get(plan_row.strategy_id)
            rows.append(_row_from_guided(plan_row, None if found is None else found[0], None if found is None else found[1]))
    report = ObservationMatrixReport(created_at=created_at, profile_id=profile_id, rows=tuple(rows), report_json_path=report_json, report_md_path=report_md)
    report_json.write_text(json.dumps(report.to_payload(), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report_md.write_text(report.to_markdown(), encoding="utf-8")
    return report




def _row_by_id(row_id: str) -> ObservationMatrixPlanRow:
    wanted = row_id.strip()
    aliases = {
        "baseline": "baseline-no-zapret",
        "pktdebug": "diagnostic-pktdebug",
        "v2": "current-v2-syndata",
        "multisplit": "reference-kartavkun-multisplit",
        "fake-tls": "reference-fake-tls-auto",
        "simple-fake": "reference-simple-fake",
    }
    wanted = aliases.get(wanted, wanted)
    for row in MATRIX_PLAN_ROWS:
        if row.row_id == wanted or row.strategy_id == wanted:
            return row
    available = ", ".join(row.row_id for row in MATRIX_PLAN_ROWS)
    raise ValueError(f"Unknown observation matrix row: {row_id}. Available rows: {available}")


def _is_root_process() -> bool:
    if os.environ.get("ZAP2_MATRIX_ROW_ALLOW_ROOT_SELECTION") == "1":
        return False
    geteuid = getattr(os, "geteuid", None)
    return bool(geteuid is not None and geteuid() == 0)


def _selected_strategy_id(root: Path, profile_id: str) -> str:
    catalog = load_workspace_catalog(root)
    try:
        return catalog.profile_by_id()[profile_id].strategy_id
    except KeyError as exc:
        raise ValueError(f"Workspace profile не найден: {profile_id}") from exc


def _baseline_runner_text(
    root: Path,
    row: ObservationMatrixPlanRow,
    *,
    seconds: int,
    interactive: bool,
    emit: Emit | None,
    input_func: InputFunc,
    endpoint_runner: EndpointWatchRunner,
) -> str:
    snapshot = runtime_nft_state_snapshot(root)
    if snapshot.saved_state == "applied" or snapshot.session_state == "running":
        return "\n".join(
            [
                "Discord observation matrix row runner",
                f"stage: {MATRIX_RUNNER_STAGE}",
                f"row: {row.row_id} — {row.label}",
                "mode: endpoint-watch-only baseline",
                "status: blocked-before-baseline",
                "reason: Zap2 runtime appears to be running/applied; baseline must be collected without Zap2 runtime.",
                "NEXT SHELL COMMANDS:",
                "  PYTHONPATH=gui python -m zap2_gui.app --default-stop-plan",
                "  PYTHONPATH=gui python -m zap2_gui.app --runtime-confirm runtime-default-<strategy>-default-stop-workflow-plan",
                "  PYTHONPATH=gui python -m zap2_gui.app --default-stop --confirm runtime-default-<strategy>-default-stop-workflow-plan",
                f"  PYTHONPATH=gui python -m zap2_gui.app --discord-observation-matrix-run-row {row.row_id}",
                "MANUAL ACTION:",
                "  Do not open Discord until the row runner asks for it.",
                "executes Discord now: no",
                "applies firewall/services now: no",
            ]
        )
    if interactive:
        if emit is not None:
            emit("Discord observation matrix row runner")
            emit(f"row: {row.row_id} — {row.label}")
            emit("MANUAL ACTION — do not type this into shell:")
            emit("  Close Discord fully. Press Enter here when Discord is closed.")
        input_func("Press Enter when Discord is closed: ")
        if emit is not None:
            emit("")
            emit("MANUAL ACTION WINDOW — do not type this into shell:")
            emit(f"  Open Discord now and wait for Checking for updates. The watcher will sample for {seconds} seconds.")
    snapshot = endpoint_runner(root=root, seconds=seconds)
    lines = [
        "Discord observation matrix row runner",
        f"stage: {MATRIX_RUNNER_STAGE}",
        f"row: {row.row_id} — {row.label}",
        "mode: endpoint-watch-only baseline",
        "status: completed",
        f"snapshot: {snapshot.output_path if snapshot.output_path is not None else 'нет'}",
        f"observations: {len(snapshot.observations)}",
        f"process lines: {len(snapshot.process_lines)}",
        "next branch: run strategy rows, then regenerate the observation matrix report.",
        "NEXT SHELL COMMAND:",
        "  PYTHONPATH=gui python -m zap2_gui.app --discord-observation-matrix-report",
        "read-only: yes",
        "applies firewall/services now: no",
    ]
    return "\n".join(lines)




def _nfqws2_binary_path(root: Path) -> Path:
    return root / "core" / "zapret2" / "nfq2" / "nfqws2"


def _nfqws2_binary_is_ready(root: Path) -> bool:
    path = _nfqws2_binary_path(root)
    return path.exists() and os.access(path, os.X_OK)


def _strategy_runner_build_needed_text(root: Path, row: ObservationMatrixPlanRow, profile_id: str) -> str:
    build_plan = prepare_default_build_plan(root=root, profile_id=profile_id)
    return "\n".join(
        [
            "Discord observation matrix row runner",
            f"stage: {MATRIX_RUNNER_STAGE}",
            f"row: {row.row_id} — {row.label}",
            f"strategy: {row.strategy_id}",
            "status: build-required",
            "meaning: nfqws2 binary is missing or not executable, so this row cannot start runtime yet.",
            f"binary: {_nfqws2_binary_path(root)}",
            "MANUAL ACTION:",
            "  Keep Discord closed. Do not launch Discord yet.",
            "NEXT SHELL COMMANDS — copy/paste in this order:",
            f"  PYTHONPATH=gui python -m zap2_gui.app --runtime-confirm {build_plan.plan_id}",
            f"  PYTHONPATH=gui python -m zap2_gui.app --default-build --confirm {build_plan.plan_id}",
            f"  PYTHONPATH=gui python -m zap2_gui.app --discord-observation-matrix-run-row {row.row_id}",
            "why no sudo here:",
            "  - local build must run as the project owner, not root; it does not mutate firewall/services.",
            "after build:",
            "  - rerunning the same row command will prepare/start the Default workflow step.",
            f"build plan id: {build_plan.plan_id}",
            f"build plan file: {build_plan.plan_path}",
            f"runtime log: {build_plan.log_path}",
            "executes Discord now: no",
            "applies firewall/services now: no",
        ]
    )

def _strategy_runner_setup_text(root: Path, row: ObservationMatrixPlanRow, profile_id: str) -> str:
    plan = prepare_default_workflow_plan(root=root, action="start", profile_id=profile_id)
    start_plan_id = plan.plan_id
    return "\n".join(
        [
            "Discord observation matrix row runner",
            f"stage: {MATRIX_RUNNER_STAGE}",
            f"row: {row.row_id} — {row.label}",
            f"strategy: {row.strategy_id}",
            "status: prepared-waiting-for-default-workflow",
            "meaning: the row strategy is selected and the start plan is prepared, but owner-rules/nfqws2 are not running yet.",
            "MANUAL ACTION:",
            "  Keep Discord closed. Do not launch Discord yet.",
            "NEXT SHELL COMMANDS:",
            f"  PYTHONPATH=gui python -m zap2_gui.app --runtime-confirm {start_plan_id}",
            f"  PYTHONPATH=gui python -m zap2_gui.app --default-start --confirm {start_plan_id}",
            f"  PYTHONPATH=gui python -m zap2_gui.app --discord-observation-matrix-run-row {row.row_id}",
            "why sudo only on the last two commands:",
            "  - strategy selection and plan preparation are non-privileged; nft counter reads need root.",
            "  - Discord must be opened only when the guided probe prints MANUAL ACTION.",
            "executes Discord now: no",
            "applies firewall/services now: no",
        ]
    )




def _strategy_runner_auto_owner_setup_text(root: Path, row: ObservationMatrixPlanRow, profile_id: str) -> str:
    """One-command-ish owner phase: select row, build if needed, prepare+confirm start plan."""

    notes: list[str] = []
    if not _nfqws2_binary_is_ready(root):
        build_plan = prepare_default_build_plan(root=root, profile_id=profile_id)
        confirm_runtime_plan(root=root, plan_id=build_plan.plan_id)
        build_result = execute_default_build(root=root, profile_id=profile_id, confirm_plan_id=build_plan.plan_id)
        notes.extend(
            [
                f"auto build plan: {build_plan.plan_id}",
                f"auto build state: {build_result.state}",
                f"auto build message: {build_result.message}",
            ]
        )
        if build_result.state != "built" or not _nfqws2_binary_is_ready(root):
            return "\n".join(
                [
                    "Discord observation matrix row runner",
                    f"stage: {MATRIX_RUNNER_STAGE}",
                    f"row: {row.row_id} — {row.label}",
                    f"strategy: {row.strategy_id}",
                    "status: auto-build-failed",
                    *notes,
                    "next branch: fix local build/dependencies before collecting this row.",
                    "executes Discord now: no",
                    "applies firewall/services now: no",
                ]
            )

    start_plan = prepare_default_workflow_plan(root=root, action="start", profile_id=profile_id)
    confirm_runtime_plan(root=root, plan_id=start_plan.plan_id)
    notes.extend(
        [
            f"auto start plan prepared+confirmed: {start_plan.plan_id}",
            f"start plan hash: {start_plan.plan_hash}",
        ]
    )
    return "\n".join(
        [
            "Discord observation matrix row runner",
            f"stage: {MATRIX_RUNNER_STAGE}",
            f"row: {row.row_id} — {row.label}",
            f"strategy: {row.strategy_id}",
            "status: auto-owner-phase-ready-for-sudo",
            "meaning: strategy is selected, nfqws2 is built, and the start workflow plan is prepared+confirmed.",
            *notes,
            "MANUAL ACTION:",
            "  Keep Discord closed. Do not launch Discord yet.",
            "NEXT SHELL COMMAND — one sudo phase:",
            f"  PYTHONPATH=gui python -m zap2_gui.app --discord-observation-matrix-run-row {row.row_id} --matrix-row-auto",
            "what the sudo phase will do:",
            "  - start Default workflow for this row using the already-confirmed plan if needed;",
            "  - run the guided probe with nft counter access;",
            "  - ask you to open Discord only at MANUAL ACTION.",
            "executes Discord now: no",
            "applies firewall/services now: no",
        ]
    )


def _strategy_runner_auto_root_text(
    root: Path,
    row: ObservationMatrixPlanRow,
    profile_id: str,
    *,
    wait_seconds: int,
    interactive: bool,
    emit: Emit | None,
) -> str:
    """Root phase: start workflow if needed, then enter guided probe."""

    if not _nfqws2_binary_is_ready(root):
        return "\n".join(
            [
                "Discord observation matrix row runner",
                f"stage: {MATRIX_RUNNER_STAGE}",
                f"row: {row.row_id} — {row.label}",
                f"strategy: {row.strategy_id}",
                "status: auto-root-blocked-build-missing",
                "meaning: nfqws2 is missing, but the local build must run as the project owner, not root.",
                "NEXT SHELL COMMAND:",
                f"  PYTHONPATH=gui python -m zap2_gui.app --discord-observation-matrix-run-row {row.row_id} --matrix-row-auto",
                "executes Discord now: no",
                "applies firewall/services now: no",
            ]
        )

    snapshot = runtime_nft_state_snapshot(root, profile_id=profile_id)
    if snapshot.saved_state != "applied" or snapshot.session_state != "running":
        plan = prepare_default_workflow_plan(root=root, action="start", profile_id=profile_id)
        try:
            confirm_runtime_plan(root=root, plan_id=plan.plan_id)
        except Exception:
            # If the owner phase already confirmed the same plan, this path should still
            # fail loudly only if the plan is invalid.  Re-raising would reduce the runner
            # to the old multi-step UX for a recoverable stale confirmation; prepare+confirm
            # above refreshes the state in normal cases.
            raise
        start_result = execute_default_workflow(root=root, action="start", profile_id=profile_id, confirm_plan_id=plan.plan_id)
        if start_result.state != "started":
            return "\n".join(
                [
                    "Discord observation matrix row runner",
                    f"stage: {MATRIX_RUNNER_STAGE}",
                    f"row: {row.row_id} — {row.label}",
                    f"strategy: {row.strategy_id}",
                    "status: auto-start-failed",
                    f"start state: {start_result.state}",
                    f"message: {start_result.message}",
                    "next branch: inspect runtime logs and owner-rules apply result before opening Discord.",
                    "executes Discord now: no",
                    "applies firewall/services now: attempted owner-confirmed start",
                ]
            )

    snapshot = runtime_nft_state_snapshot(root, profile_id=profile_id)
    if snapshot.active_strategy_id != row.strategy_id:
        return "\n".join(
            [
                "Discord observation matrix row runner",
                f"stage: {MATRIX_RUNNER_STAGE}",
                f"row: {row.row_id} — {row.label}",
                f"expected strategy: {row.strategy_id}",
                f"active/applied strategy: {snapshot.active_strategy_id}",
                "status: auto-root-blocked-active-strategy-mismatch",
                "meaning: runtime is running, but not with this row strategy. Stop workflow and rerun the owner phase for the row.",
                "executes Discord now: no",
                "applies firewall/services now: no",
            ]
        )

    from .discord_pretls_guided_probe import runtime_discord_pretls_guided_probe_to_text

    text = runtime_discord_pretls_guided_probe_to_text(
        root=root,
        profile_id=profile_id,
        wait_seconds=wait_seconds,
        interactive=interactive,
        emit=emit,
    )
    return "\n\n".join(
        [
            text,
            "Matrix row runner auto post-step",
            f"row: {row.row_id}",
            "MANUAL ACTION:",
            "  After the probe report is written, close Discord, then stop Default workflow before moving to the next row.",
            "NEXT SHELL COMMAND:",
            "  PYTHONPATH=gui python -m zap2_gui.app --discord-observation-matrix-report",
        ]
    )

def discord_observation_matrix_run_row_to_text(
    row_id: str,
    root: Path | None = None,
    profile_id: str = "default",
    *,
    wait_seconds: int = DEFAULT_MATRIX_ROW_SECONDS,
    interactive: bool = True,
    auto: bool = False,
    emit: Emit | None = None,
    input_func: InputFunc = input,
    endpoint_runner: EndpointWatchRunner = run_discord_endpoint_watch,
) -> str:
    """Run or prepare exactly one observation-matrix row.

    This is Stage 7o2a's UX simplification layer.  It does not silently start
    privileged firewall state.  Instead it selects/prepares when safe, refuses
    invalid states, and runs the existing guided probe only when the workflow is
    already alive and this process has enough privileges to read nft counters.
    """

    layout = discover_layout(root)
    row = _row_by_id(row_id)
    wait_seconds = max(0, min(int(wait_seconds), 600))
    if row.strategy_id is None:
        return _baseline_runner_text(
            layout.root,
            row,
            seconds=wait_seconds,
            interactive=interactive,
            emit=emit,
            input_func=input_func,
            endpoint_runner=endpoint_runner,
        )

    if _is_root_process():
        selected = _selected_strategy_id(layout.root, profile_id)
        if selected != row.strategy_id:
            return "\n".join(
                [
                    "Discord observation matrix row runner",
                    f"stage: {MATRIX_RUNNER_STAGE}",
                    f"row: {row.row_id} — {row.label}",
                    "status: blocked-root-selection",
                    "reason: this command is running as root, but the row strategy is not selected. Refusing to write .zap2 strategy selection as root.",
                    "NEXT SHELL COMMAND:",
                    f"  PYTHONPATH=gui python -m zap2_gui.app --discord-observation-matrix-run-row {row.row_id}" + (" --matrix-row-auto" if auto else ""),
                    "executes Discord now: no",
                    "applies firewall/services now: no",
                ]
            )
        if auto:
            return _strategy_runner_auto_root_text(
                layout.root,
                row,
                profile_id,
                wait_seconds=wait_seconds,
                interactive=interactive,
                emit=emit,
            )
    else:
        selected = _selected_strategy_id(layout.root, profile_id)
        if selected != row.strategy_id:
            select_workspace_strategy(layout.root, strategy_id=row.strategy_id or "", profile_id=profile_id, reason=f"stage7o2a-matrix-row:{row.row_id}")
        if auto:
            return _strategy_runner_auto_owner_setup_text(layout.root, row, profile_id)

    if not _nfqws2_binary_is_ready(layout.root):
        if _is_root_process():
            return "\n".join(
                [
                    "Discord observation matrix row runner",
                    f"stage: {MATRIX_RUNNER_STAGE}",
                    f"row: {row.row_id} — {row.label}",
                    f"strategy: {row.strategy_id}",
                    "status: build-required-under-root",
                    "meaning: nfqws2 binary is missing, but local build must not be performed as root.",
                    f"binary: {_nfqws2_binary_path(layout.root)}",
                    "NEXT SHELL COMMAND:",
                    f"  PYTHONPATH=gui python -m zap2_gui.app --discord-observation-matrix-run-row {row.row_id}",
                    "MANUAL ACTION:",
                    "  Keep Discord closed. Do not launch Discord yet.",
                    "executes Discord now: no",
                    "applies firewall/services now: no",
                ]
            )
        return _strategy_runner_build_needed_text(layout.root, row, profile_id)

    snapshot = runtime_nft_state_snapshot(layout.root, profile_id=profile_id)
    if snapshot.saved_state != "applied" or snapshot.session_state != "running":
        if _is_root_process():
            return "\n".join(
                [
                    "Discord observation matrix row runner",
                    f"stage: {MATRIX_RUNNER_STAGE}",
                    f"row: {row.row_id} — {row.label}",
                    f"strategy: {row.strategy_id}",
                    "status: workflow-not-running-under-root",
                    "meaning: root can read nft counters, but Default workflow is not running; start it from the owner-confirmed path first.",
                    "NEXT SHELL COMMAND:",
                    f"  PYTHONPATH=gui python -m zap2_gui.app --discord-observation-matrix-run-row {row.row_id}",
                    "executes Discord now: no",
                    "applies firewall/services now: no",
                ]
            )
        return _strategy_runner_setup_text(layout.root, row, profile_id)

    if snapshot.active_strategy_id != row.strategy_id:
        return "\n".join(
            [
                "Discord observation matrix row runner",
                f"stage: {MATRIX_RUNNER_STAGE}",
                f"row: {row.row_id} — {row.label}",
                f"expected strategy: {row.strategy_id}",
                f"active/applied strategy: {snapshot.active_strategy_id}",
                "status: blocked-active-strategy-mismatch",
                "meaning: Default workflow is already running with a different strategy. Stop it, then rerun this row runner.",
                "NEXT SHELL COMMANDS:",
                "  PYTHONPATH=gui python -m zap2_gui.app --default-stop-plan",
                "  PYTHONPATH=gui python -m zap2_gui.app --runtime-confirm runtime-default-<active-strategy>-default-stop-workflow-plan",
                "  PYTHONPATH=gui python -m zap2_gui.app --default-stop --confirm runtime-default-<active-strategy>-default-stop-workflow-plan",
                f"  PYTHONPATH=gui python -m zap2_gui.app --discord-observation-matrix-run-row {row.row_id}",
                "executes Discord now: no",
                "applies firewall/services now: no",
            ]
        )

    if not _is_root_process():
        return "\n".join(
            [
                "Discord observation matrix row runner",
                f"stage: {MATRIX_RUNNER_STAGE}",
                f"row: {row.row_id} — {row.label}",
                f"strategy: {row.strategy_id}",
                "status: ready-needs-sudo-for-guided-probe",
                "meaning: workflow is running with the correct strategy, but nft counter reads require root.",
                "NEXT SHELL COMMAND:",
                f"  PYTHONPATH=gui python -m zap2_gui.app --discord-observation-matrix-run-row {row.row_id}",
                "MANUAL ACTION:",
                "  Keep Discord closed until the guided probe prints MANUAL ACTION.",
                "executes Discord now: no",
                "applies firewall/services now: no",
            ]
        )

    from .discord_pretls_guided_probe import runtime_discord_pretls_guided_probe_to_text

    text = runtime_discord_pretls_guided_probe_to_text(
        root=layout.root,
        profile_id=profile_id,
        wait_seconds=wait_seconds,
        interactive=interactive,
        emit=emit,
    )
    return "\n\n".join(
        [
            text,
            "Matrix row runner post-step",
            f"row: {row.row_id}",
            "MANUAL ACTION:",
            "  After the probe report is written, close Discord, then stop Default workflow before moving to the next row.",
            "NEXT SHELL COMMAND:",
            "  PYTHONPATH=gui python -m zap2_gui.app --discord-observation-matrix-report",
        ]
    )

def discord_observation_matrix_plan_to_text(root: Path | None = None, profile_id: str = "default") -> str:
    layout = discover_layout(root)
    catalog = load_strategy_catalog(layout.root).by_id()
    lines = [
        "Discord observation matrix plan",
        f"profile: {profile_id}",
        "stage: v0.4-alpha Stage 7o2",
        "purpose: compare baseline, diagnostic and external-reference candidates in one report format before promoting any strategy.",
        "executes now: no",
        "applies firewall/services now: no",
        "starts Discord now: no",
        "",
        "Rows:",
    ]
    for index, row in enumerate(MATRIX_PLAN_ROWS, start=1):
        available = "yes" if row.strategy_id is None or row.strategy_id in catalog else "no"
        lines.extend([
            f"{index}. {row.label}",
            f"   row id: {row.row_id}",
            f"   mode: {row.mode}",
            f"   strategy: {row.strategy_id or 'none'} (available: {available})",
            f"   purpose: {row.purpose}",
            "   SHELL COMMAND:",
            f"     {row.run_command}",
            f"   expected evidence: {row.expected_evidence}",
            "",
        ])
    lines.extend([
        "Simplified row runner:",
        "  PYTHONPATH=gui python -m zap2_gui.app --discord-observation-matrix-run-row <row id>",
        "  The runner selects/prepares the row, tells you when workflow must be started, and runs the guided probe when the state is valid.",
        "",
        "Manual fallback loop per strategy row:",
        "  1. Close Discord fully.",
        "  2. Select the row strategy with --select-strategy when the row has a strategy.",
        "  3. Start Default workflow through the existing owner-confirmed path.",
        "  4. Run the guided probe with sudo for nft counter reads.",
        "  5. Open Discord only when the probe prints MANUAL ACTION.",
        "  6. Save the generated report, stop workflow, move to the next row.",
        "",
        "After collecting rows:",
        "  PYTHONPATH=gui python -m zap2_gui.app --discord-observation-matrix-report",
        "",
        "Do not compare strategies by memory or screenshots only; compare generated row reports.",
    ])
    return "\n".join(lines)


def discord_observation_matrix_report_to_text(root: Path | None = None, profile_id: str = "default") -> str:
    return collect_observation_matrix(root=root, profile_id=profile_id).to_text()
