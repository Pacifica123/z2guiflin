"""GUI-first runtime overview state.

This adapter is deliberately read-only.  It gives the PyQt Overview tab one
compact state model instead of making the user compare plan ids, nft snapshots,
process status and active strategy files by hand.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .runtime_default import default_workflow_status
from .runtime_nft_state import runtime_nft_state_snapshot
from .runtime_state import ensure_runtime_store
from .strategy_file_inputs import strategy_file_dependency_blockers
from .workspace_profiles import load_workspace_catalog
from ..project_paths import discover_layout


@dataclass(frozen=True)
class GuiFirstRuntimeOverviewRow:
    """Single user-facing row for the Overview status table."""

    section: str
    field: str
    value: str
    status: str

    def as_tuple(self) -> tuple[str, str, str, str]:
        return (self.section, self.field, self.value, self.status)


@dataclass(frozen=True)
class GuiFirstRuntimeOverview:
    """One-screen state for the user-facing Overview tab."""

    profile_id: str
    selected_strategy_id: str
    prepared_start_plan_id: str
    prepared_start_plan_strategy_id: str
    prepared_start_plan_state: str
    running_strategy_id: str
    workflow_state: str
    session_state: str
    session_pid: int | None
    owner_rules_state: str
    owner_rules_strategy_id: str
    nft_table: str
    nfqueue_num: int
    state: str
    primary_action: str
    primary_action_label: str
    issues: tuple[str, ...]
    next_gui_action: str
    developer_hint: str

    @property
    def is_running(self) -> bool:
        return self.state == "running"

    @property
    def has_mismatch(self) -> bool:
        return self.state in {"mismatch", "partial", "stale"}


    def table_rows(self, *, developer: bool = False) -> tuple[GuiFirstRuntimeOverviewRow, ...]:
        """Rows for the GUI table view.

        The table is intentionally redundant with ``to_text``: the GUI can show
        a compact visual view while the neighbouring copy button still exposes a
        plain-text representation that is easy to paste into an issue or chat.
        """

        plan_status = "ok"
        if self.prepared_start_plan_state == "none":
            plan_status = "missing"
        elif self.prepared_start_plan_state == "stale":
            plan_status = "stale"
        elif self.prepared_start_plan_state == "ready-unconfirmed":
            plan_status = "needs-confirmation"

        running_value = self.running_strategy_id or "нет"
        running_status = "ok" if self.running_strategy_id in {"", self.selected_strategy_id} else "mismatch"
        session_value = self.session_state
        if self.session_pid is not None:
            session_value = f"{self.session_state} / pid {self.session_pid}"
        session_status = "ok" if self.session_state == "running" else ("stopped" if self.session_state in {"stopped", "not-started"} else "attention")
        owner_status = "ok" if self.owner_rules_state == "applied" else ("stopped" if self.owner_rules_state in {"reverted", "not-applied"} else "attention")
        owner_strategy_status = "ok" if self.owner_rules_strategy_id in {"", self.selected_strategy_id} else "mismatch"
        overall_status = "ok" if self.state == "running" else ("stopped" if self.state == "stopped" else "attention")

        rows: list[GuiFirstRuntimeOverviewRow] = [
            GuiFirstRuntimeOverviewRow("Профиль", "Workspace profile", self.profile_id, "info"),
            GuiFirstRuntimeOverviewRow("Стратегия", "Выбрана в GUI", self.selected_strategy_id, "ok"),
            GuiFirstRuntimeOverviewRow("Стратегия", "Start-plan", self.prepared_start_plan_strategy_id or "нет", plan_status),
            GuiFirstRuntimeOverviewRow("Стратегия", "Запущена", running_value, running_status),
            GuiFirstRuntimeOverviewRow("Workflow", "Default workflow", self.workflow_state, "ok" if self.workflow_state == "started" else "stopped"),
            GuiFirstRuntimeOverviewRow("Workflow", "nfqws2 session", session_value, session_status),
            GuiFirstRuntimeOverviewRow("Firewall", "Owner-rules", self.owner_rules_state, owner_status),
            GuiFirstRuntimeOverviewRow("Firewall", "Owner-rules strategy", self.owner_rules_strategy_id or "нет", owner_strategy_status),
            GuiFirstRuntimeOverviewRow("Firewall", "NFQUEUE", f"{self.nfqueue_num} / inet {self.nft_table}", "info"),
            GuiFirstRuntimeOverviewRow("Итог", "Состояние", self.state, overall_status),
            GuiFirstRuntimeOverviewRow("Итог", "Следующее действие", self.next_gui_action, "action"),
        ]
        if self.issues:
            for index, issue in enumerate(self.issues, start=1):
                rows.append(GuiFirstRuntimeOverviewRow("Проблемы", f"Issue {index}", issue, "attention"))
        else:
            rows.append(GuiFirstRuntimeOverviewRow("Проблемы", "Issues", "нет", "ok"))
        if developer:
            rows.extend(
                [
                    GuiFirstRuntimeOverviewRow("Dev", "Start plan id", self.prepared_start_plan_id or "нет", "info"),
                    GuiFirstRuntimeOverviewRow("Dev", "Session pid", str(self.session_pid) if self.session_pid is not None else "нет", "info"),
                    GuiFirstRuntimeOverviewRow("Dev", "Hint", self.developer_hint, "info"),
                ]
            )
        return tuple(rows)

    def to_table_text(self, *, developer: bool = False) -> str:
        """Plain text copy of the GUI table, tab-separated for readable paste."""

        lines = ["section\tfield\tvalue\tstatus"]
        for row in self.table_rows(developer=developer):
            safe = [part.replace("\t", " ").replace("\n", " ") for part in row.as_tuple()]
            lines.append("\t".join(safe))
        return "\n".join(lines)


    def to_text(self, *, developer: bool = False) -> str:
        issues = [f"  - {issue}" for issue in self.issues] or ["  - нет"]
        lines = [
            "GUI-first runtime overview",
            f"profile: {self.profile_id}",
            f"selected strategy: {self.selected_strategy_id}",
            f"prepared start plan: {self.prepared_start_plan_state}",
            f"prepared start strategy: {self.prepared_start_plan_strategy_id or 'нет'}",
            f"workflow state: {self.workflow_state}",
            f"running strategy: {self.running_strategy_id or 'нет'}",
            f"session: {self.session_state}",
            f"owner-rules: {self.owner_rules_state}",
            f"owner-rules strategy: {self.owner_rules_strategy_id or 'нет'}",
            f"overall state: {self.state}",
            f"primary GUI action: {self.primary_action_label}",
            f"next GUI action: {self.next_gui_action}",
            "issues:",
            *issues,
            "user mode: no shell commands are required for the next step",
            "read-only: yes",
            "executes now: no",
            "mutates services/firewall now: no",
        ]
        if developer:
            lines.extend(
                [
                    "",
                    "Developer details:",
                    f"prepared start plan id: {self.prepared_start_plan_id or 'нет'}",
                    f"nft table: inet {self.nft_table}",
                    f"nfqueue: {self.nfqueue_num}",
                    f"session pid: {self.session_pid if self.session_pid is not None else 'нет'}",
                    f"developer hint: {self.developer_hint}",
                ]
            )
        return "\n".join(lines)


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _expected_default_plan_id(profile_id: str, strategy_id: str) -> str:
    return f"runtime-{profile_id}-{strategy_id}-default-start-workflow-plan"


def _prepared_start_plan(paths_root: Path, profile_id: str, selected_strategy_id: str) -> tuple[str, str, str]:
    paths = ensure_runtime_store(paths_root)
    expected_id = _expected_default_plan_id(profile_id, selected_strategy_id)
    expected_path = paths.plans_dir / f"{expected_id}.json"
    if expected_path.is_file():
        data = _read_json(expected_path)
        if data.get("confirmed") is True:
            return expected_id, str(data.get("strategyId") or selected_strategy_id), "ready-confirmed"
        return expected_id, str(data.get("strategyId") or selected_strategy_id), "ready-unconfirmed"

    latest_path: Path | None = None
    latest_mtime = -1.0
    pattern = f"runtime-{profile_id}-*-default-start-workflow-plan.json"
    if paths.plans_dir.is_dir():
        for candidate in paths.plans_dir.glob(pattern):
            try:
                mtime = candidate.stat().st_mtime
            except OSError:
                continue
            if mtime > latest_mtime:
                latest_path = candidate
                latest_mtime = mtime
    if latest_path is None:
        return "", "", "none"
    data = _read_json(latest_path)
    return str(data.get("planId") or latest_path.stem), str(data.get("strategyId") or ""), "stale"


def _workflow_record(paths_root: Path, profile_id: str) -> dict[str, Any]:
    paths = ensure_runtime_store(paths_root)
    return _read_json(paths.sessions_dir / f"{profile_id}.default-workflow.json")


def gui_first_runtime_overview(root: Path | None = None, profile_id: str = "default") -> GuiFirstRuntimeOverview:
    layout = discover_layout(root)
    paths = ensure_runtime_store(layout.root)
    catalog = load_workspace_catalog(layout.root)
    profiles = catalog.profile_by_id()
    if profile_id not in profiles:
        raise ValueError(f"Неизвестный workspace-профиль: {profile_id}")
    selected_strategy_id = profiles[profile_id].strategy_id
    selected_strategy = catalog.strategy_by_id().get(selected_strategy_id)
    strategy_file_blockers = () if selected_strategy is None else strategy_file_dependency_blockers(paths.root, selected_strategy.runtime_args)
    plan_id, plan_strategy_id, plan_state = _prepared_start_plan(paths.root, profile_id, selected_strategy_id)
    workflow_status = default_workflow_status(paths.root, profile_id=profile_id)
    nft_snapshot = runtime_nft_state_snapshot(paths.root, profile_id=profile_id)
    workflow_record = _workflow_record(paths.root, profile_id)
    running_strategy_id = ""
    if workflow_status.workflow_state in {"started", "stale"}:
        running_strategy_id = str(workflow_record.get("strategyId") or "")

    issues: list[str] = []
    state = "stopped"
    primary_action = "start"
    primary_label = "Включить выбранную стратегию"
    next_gui_action = "Нажать основную кнопку Overview: «Включить выбранную стратегию»."
    developer_hint = "Developer mode can show plan ids, nft table and raw runtime logs."

    workflow_started = workflow_status.workflow_state == "started" and workflow_status.session_status.state == "running"
    owner_applied = nft_snapshot.saved_state == "applied"
    session_running = workflow_status.session_status.state == "running"

    if workflow_started and owner_applied:
        if running_strategy_id and running_strategy_id != selected_strategy_id:
            state = "mismatch"
            primary_action = "restart"
            primary_label = "Перезапустить с выбранной стратегией"
            next_gui_action = "Нажать «Отключить Default», затем «Включить выбранную стратегию»; GUI сам пересоберёт план."
            issues.append(f"Запущена стратегия {running_strategy_id}, а выбрана {selected_strategy_id}.")
        elif nft_snapshot.active_strategy_id != selected_strategy_id:
            state = "mismatch"
            primary_action = "restart"
            primary_label = "Перезапустить правила под выбранную стратегию"
            next_gui_action = "Отключить и снова включить Default workflow из Overview."
            issues.append(f"Owner-rules применены для {nft_snapshot.active_strategy_id}, выбрана {selected_strategy_id}.")
        else:
            state = "running"
            primary_action = "stop"
            primary_label = "Отключить Default"
            next_gui_action = "Для проверки Discord нажать GUI-кнопку проверки Discord; консоль не нужна."
    elif owner_applied and not session_running:
        state = "partial"
        primary_action = "stop"
        primary_label = "Снять правила и сбросить состояние"
        next_gui_action = "Нажать основную кнопку Overview для безопасного stop/revert, затем включить снова."
        issues.append("Firewall/NFQUEUE rules применены, но nfqws2 session не running.")
    elif session_running and not owner_applied:
        state = "partial"
        primary_action = "stop"
        primary_label = "Остановить зависшую session"
        next_gui_action = "Нажать основную кнопку Overview для stop, затем включить снова."
        issues.append("nfqws2 session running, но owner-rules не applied.")
    elif workflow_status.workflow_state == "stale":
        state = "stale"
        primary_action = "restart"
        primary_label = "Сбросить stale-состояние"
        next_gui_action = "Нажать основную кнопку Overview: GUI выполнит stop/revert, затем можно включить заново."
        issues.append(workflow_status.message)
    else:
        if plan_state == "none":
            issues.append("Start-plan для выбранной стратегии ещё не подготовлен; GUI подготовит его сам при включении.")
        elif plan_state == "stale":
            issues.append(f"Последний start-plan относится к {plan_strategy_id or 'другой стратегии'}, а выбрана {selected_strategy_id}.")
            primary_label = "Пересобрать план и включить"
        elif plan_state == "ready-unconfirmed":
            issues.append("Start-plan подготовлен, но ещё не подтверждён; GUI подтвердит его перед privileged start.")

    if strategy_file_blockers:
        preview = ", ".join(item.value for item in strategy_file_blockers[:3])
        if len(strategy_file_blockers) > 3:
            preview += f", … ещё {len(strategy_file_blockers) - 3}"
        issues.append(f"У выбранной стратегии отсутствуют обязательные hostlist/ipset files: {preview}.")
        if state == "stopped":
            primary_action = "blocked"
            primary_label = "Запуск заблокирован: нет файлов списков"
            next_gui_action = "Повторно импортировать TXT вместе с каталогом lists/ipset либо добавить отсутствующие файлы в workspace."

    return GuiFirstRuntimeOverview(
        profile_id=profile_id,
        selected_strategy_id=selected_strategy_id,
        prepared_start_plan_id=plan_id,
        prepared_start_plan_strategy_id=plan_strategy_id,
        prepared_start_plan_state=plan_state,
        running_strategy_id=running_strategy_id,
        workflow_state=workflow_status.workflow_state,
        session_state=workflow_status.session_status.state,
        session_pid=workflow_status.session_status.pid,
        owner_rules_state=nft_snapshot.saved_state,
        owner_rules_strategy_id=nft_snapshot.active_strategy_id,
        nft_table=nft_snapshot.nft_table,
        nfqueue_num=nft_snapshot.nfqueue_num,
        state=state,
        primary_action=primary_action,
        primary_action_label=primary_label,
        issues=tuple(issues),
        next_gui_action=next_gui_action,
        developer_hint=developer_hint,
    )


def gui_first_runtime_overview_to_text(root: Path | None = None, profile_id: str = "default", *, developer: bool = False) -> str:
    return gui_first_runtime_overview(root=root, profile_id=profile_id).to_text(developer=developer)


def gui_first_runtime_overview_to_table_text(root: Path | None = None, profile_id: str = "default", *, developer: bool = False) -> str:
    return gui_first_runtime_overview(root=root, profile_id=profile_id).to_table_text(developer=developer)
