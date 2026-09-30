"""P04d legacy flat-CLI compatibility grammar.

Every historical top-level action selector now translates to a canonical
ActionContract before execution. The compatibility grammar remains accepted,
but there are no legacy-only selectors and first-match ordering is no longer an
action authority. Canonical actions that need the old selector operand use
``--operand`` and are materialized only inside the selected contract handler.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..models.action_catalog import ACTION_CONTRACT_BY_ID
from ..models.action_bindings import GENERATED_BINDING_BY_SELECTOR


# Exactly the argparse destinations referenced by top-level dispatch branches in
# the post-P04b app.py. P04c acceptance AST-checks this tuple against main().
# P04d removes this transitional inventory as 100% actions become contract-backed.
LEGACY_SELECTOR_DESTS: tuple[str, ...] = (
    "gui",
    "build_plan",
    "security_blocklist_status",
    "security_blocklist_enable",
    "security_blocklist_enable_inbound",
    "security_blocklist_disable",
    "security_blocklist_update",
    "security_blocklist_apply",
    "security_blocklist_refresh",
    "security_blocklist_timer_plan",
    "security_blocklist_install_timer",
    "security_blocklist_remove_timer",
    "launch_composer_status",
    "launch_composer_plan",
    "launch_composer_start",
    "launch_composer_stop",
    "discord_verification_plan",
    "discord_verification_template",
    "discord_endpoint_plan",
    "discord_endpoint_watch",
    "discord_endpoint_report",
    "discord_netlog_plan",
    "har_plan",
    "har_analyze",
    "har_report",
    "har_workbench",
    "har_workbench_report",
    "har_group_plan",
    "discord_har_plan",
    "discord_har_analyze",
    "discord_har_report",
    "discord_har_workbench",
    "discord_har_workbench_report",
    "discord_har_group_plan",
    "discord_voice_profiles",
    "discord_dns_edge_plan",
    "discord_dns_edge_check",
    "external_reference_audit",
    "tunnel_connection_import_vless",
    "tunnel_connections",
    "tunnel_select_connection",
    "tor_backend_plan",
    "tor_backend_start",
    "tor_backend_status",
    "tor_backend_stop",
    "discord_tunnel_plan",
    "discord_tunnel_core_preflight",
    "discord_tunnel_start",
    "discord_tunnel_stop",
    "discord_tunnel_status",
    "discord_tunnel_probe",
    "discord_tunnel_https_probe",
    "discord_tunnel_route_diagnose",
    "discord_tunnel_evidence",
    "discord_tunnel_guided_run",
    "discord_tunnel_tun_plan",
    "discord_proxy_route_plan",
    "discord_launch_through_socks",
    "discord_stop_launched",
    "strategy_parser_preflight",
    "runtime_contracts",
    "runtime_plan",
    "validate_runtime_contracts",
    "runtime_prepare",
    "runtime_confirm",
    "runtime_log",
    "runtime_logs",
    "runtime_apply_plan",
    "runtime_revert_plan",
    "runtime_apply",
    "runtime_revert",
    "runtime_reconcile",
    "runtime_session_start",
    "runtime_session_status",
    "runtime_session_stop",
    "runtime_nft_state",
    "runtime_pretls_probe",
    "runtime_discord_pretls_guided_probe",
    "discord_observation_matrix_plan",
    "discord_observation_matrix_report",
    "discord_observation_matrix_run_row",
    "service_plan",
    "service_apply",
    "default_build_deps",
    "default_build_plan",
    "default_build",
    "default_start_plan",
    "default_stop_plan",
    "default_start",
    "privileged_executor_status",
    "privileged_executor_install_plan",
    "runtime_migrate_state",
    "runtime_kernel_status",
    "default_status",
    "gui_first_overview",
    "gui_privileged_command",
    "default_stop",
    "blockcheck_preflight",
    "blockcheck_plan",
    "blockcheck_build_plan",
    "blockcheck_build",
    "blockcheck_run",
    "blockcheck_last_log",
    "blockcheck_coverage",
    "blockcheck_service_policy",
    "blockcheck_tournament",
    "blockcheck_validate_strategy_plan",
    "blockcheck_export_strategies",
    "select_preset",
    "select_strategy",
    "list_presets",
    "show_preset",
    "show_preset_profile",
    "list_profiles",
    "show_profile",
    "list_strategies",
    "show_strategy",
)


STATIC_MIGRATED_SELECTOR_MAP: dict[str, str] = {
    "runtime_contracts": "runtime.contracts.show",
    "validate_runtime_contracts": "runtime.contracts.validate",
    "runtime_log": "runtime.logs.show",
    "runtime_logs": "runtime.logs.snapshot",
    "runtime_apply_plan": "runtime.owner-rules.plan.apply",
    "runtime_revert_plan": "runtime.owner-rules.plan.revert",
    "runtime_apply": "runtime.owner-rules.apply",
    "runtime_revert": "runtime.owner-rules.revert",
    "runtime_reconcile": "runtime.owner-rules.reconcile",
    "runtime_session_start": "runtime.session.start",
    "runtime_session_status": "runtime.session.status",
    "runtime_session_stop": "runtime.session.stop",
    "runtime_nft_state": "runtime.nft-state.show",
    "runtime_kernel_status": "runtime.kernel.status",
    "default_build_deps": "default.build.dependencies.inspect",
    "default_build_plan": "default.build.plan",
    "default_build": "default.build.apply",
    "default_start_plan": "default.workflow.plan.start",
    "default_stop_plan": "default.workflow.plan.stop",
    "default_start": "default.workflow.start",
    "default_status": "default.workflow.status",
    "default_stop": "default.workflow.stop",
    "privileged_executor_status": "privileged.executor.status",
    "privileged_executor_install_plan": "privileged.executor.install-plan",
    "gui_first_overview": "gui.overview.show",
}


@dataclass(frozen=True)
class CliActionResolution:
    canonical_action_id: str | None
    legacy_selector: str | None
    active_selectors: tuple[str, ...]

    @property
    def migrated(self) -> bool:
        return self.canonical_action_id is not None

    @property
    def legacy_only(self) -> bool:
        return self.legacy_selector is not None and self.canonical_action_id is None


def _selector_active(value: Any) -> bool:
    if value is None or value is False:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (tuple, list, set, dict)):
        return bool(value)
    return bool(value)


def active_legacy_selectors(args: Any) -> tuple[str, ...]:
    return tuple(dest for dest in LEGACY_SELECTOR_DESTS if _selector_active(getattr(args, dest, None)))


def _translate_migrated_selector(selector: str, args: Any) -> str | None:
    if selector == "runtime_plan":
        action = str(getattr(args, "runtime_plan", "") or "").strip()
        candidate = f"runtime.plan.{action}"
        return candidate if candidate in ACTION_CONTRACT_BY_ID else None
    if selector in STATIC_MIGRATED_SELECTOR_MAP:
        return STATIC_MIGRATED_SELECTOR_MAP[selector]
    binding = GENERATED_BINDING_BY_SELECTOR.get(selector)
    return binding.action_id if binding is not None else None


def resolve_cli_action(args: Any) -> CliActionResolution:
    """Resolve exactly one selector before any action handler can execute.

    ``--action`` is the canonical selector. Legacy selectors remain accepted as
    compatibility grammar, but combining canonical+legacy or multiple legacy
    selectors is rejected even when two spellings would resolve to the same
    ActionContract. Options/modifiers such as ``--profile`` and ``--confirm``
    are intentionally not selectors.
    """

    legacy = active_legacy_selectors(args)
    canonical = str(getattr(args, "action", "") or "").strip() or None
    operands = tuple(str(value) for value in (getattr(args, "operand", ()) or ()))
    if operands and not canonical:
        raise ValueError("--operand requires canonical --action; legacy selectors carry their own operand value")
    selector_tokens = (("action",) if canonical else ()) + legacy
    if len(selector_tokens) > 1:
        pretty = ["--action" if item == "action" else "--" + item.replace("_", "-") for item in selector_tokens]
        raise ValueError(
            "Contradictory action selectors: " + ", ".join(pretty) + ". Choose exactly one operation/action."
        )
    if canonical:
        if canonical not in ACTION_CONTRACT_BY_ID:
            raise ValueError(f"Unknown ActionContract: {canonical}")
        return CliActionResolution(canonical, None, selector_tokens)
    if not legacy:
        return CliActionResolution(None, None, ())
    selector = legacy[0]
    return CliActionResolution(_translate_migrated_selector(selector, args), selector, legacy)


def migrated_legacy_selectors() -> tuple[str, ...]:
    """All historical top-level selectors are contract-backed in P04d."""

    return tuple(sorted(LEGACY_SELECTOR_DESTS))


def remaining_legacy_only_selectors() -> tuple[str, ...]:
    return tuple(selector for selector in LEGACY_SELECTOR_DESTS if selector not in migrated_legacy_selectors())
