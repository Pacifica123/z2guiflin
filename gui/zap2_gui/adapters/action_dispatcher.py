"""P04c canonical ActionContract dispatcher.

The dispatcher is the executable authority for the bounded P04c action slice.
CLI and GUI project the same ActionContracts. Legacy CLI spellings are resolved
before this module is called; handlers never inspect competing selector flags.
"""
from __future__ import annotations

import sys
from typing import Any, Callable

from ..models.action_catalog import ACTION_CONTRACT_BY_ID, P04C_ACTION_CONTRACTS
from .runtime_contracts import runtime_contracts_to_text, validate_runtime_contracts_to_text
from .runtime_plan_generator import runtime_plan_to_text
from .runtime_state import runtime_log_to_text
from .runtime_logs import runtime_log_snapshot_to_text
from .runtime_apply import prepare_runtime_owner_rules_plan, reconcile_runtime_owner_rules
from .runtime_session import runtime_session_status, stop_runtime_session
from .runtime_nft_state import runtime_nft_state_to_text
from .runtime_default import default_workflow_status, prepare_default_workflow_plan
from .runtime_default_build import execute_default_build, prepare_default_build_plan
from .build_dependencies import run_build_dependency_preflight
from .runtime_kernel import runtime_kernel_status
from .gui_first_overview import gui_first_runtime_overview_to_text
from .privileged_executor import (
    execute_bounded_default_workflow,
    execute_bounded_owner_rules,
    execute_bounded_session_start,
    privileged_executor_install_command,
    privileged_executor_status,
)

ActionHandler = Callable[[Any], int]


def _print(text: object) -> int:
    print(text)
    return 0


def _runtime_plan(action: str) -> ActionHandler:
    def handler(args: Any) -> int:
        return _print(runtime_plan_to_text(action=action, profile_id=args.profile))

    return handler


def _runtime_contracts_show(args: Any) -> int:
    del args
    return _print(runtime_contracts_to_text())


def _runtime_contracts_validate(args: Any) -> int:
    del args
    text = validate_runtime_contracts_to_text()
    print(text)
    return 0 if "FAILED" not in text else 1


def _runtime_log(args: Any) -> int:
    return _print(runtime_log_to_text(profile_id=args.profile))


def _runtime_logs(args: Any) -> int:
    return _print(runtime_log_snapshot_to_text(profile_id=args.profile))


def _owner_rules_plan(action: str) -> ActionHandler:
    def handler(args: Any) -> int:
        return _print(prepare_runtime_owner_rules_plan(action=action, profile_id=args.profile).to_text())

    return handler


def _owner_rules_execute(action: str) -> ActionHandler:
    def handler(args: Any) -> int:
        return _print(
            execute_bounded_owner_rules(
                action=action,
                profile_id=args.profile,
                confirm_plan_id=args.confirm or "",
            ).to_text()
        )

    return handler


def _owner_rules_reconcile(args: Any) -> int:
    return _print(reconcile_runtime_owner_rules(profile_id=args.profile).to_text())


def _runtime_session_start(args: Any) -> int:
    return _print(execute_bounded_session_start(profile_id=args.profile).to_text())


def _runtime_session_status(args: Any) -> int:
    return _print(runtime_session_status(profile_id=args.profile).to_text())


def _runtime_session_stop(args: Any) -> int:
    return _print(stop_runtime_session(profile_id=args.profile).to_text())


def _runtime_nft_state(args: Any) -> int:
    return _print(runtime_nft_state_to_text(profile_id=args.profile))


def _runtime_kernel_status(args: Any) -> int:
    return _print(runtime_kernel_status(profile_id=args.profile).to_text())


def _default_build_deps(args: Any) -> int:
    del args
    return _print(run_build_dependency_preflight("nfqws2").to_text())


def _default_build_plan(args: Any) -> int:
    return _print(prepare_default_build_plan(profile_id=args.profile).to_text())


def _default_build(args: Any) -> int:
    return _print(execute_default_build(profile_id=args.profile, confirm_plan_id=args.confirm or "").to_text())


def _default_workflow_plan(action: str) -> ActionHandler:
    def handler(args: Any) -> int:
        return _print(prepare_default_workflow_plan(action=action, profile_id=args.profile).to_text())

    return handler


def _default_workflow_execute(action: str, expected_state: str) -> ActionHandler:
    def handler(args: Any) -> int:
        result = execute_bounded_default_workflow(
            action=action,
            profile_id=args.profile,
            confirm_plan_id=args.confirm or "",
        )
        print(result.to_text())
        return 0 if result.state == expected_state else 1

    return handler


def _default_status(args: Any) -> int:
    return _print(default_workflow_status(profile_id=args.profile).to_text())


def _privileged_executor_status(args: Any) -> int:
    del args
    return _print(privileged_executor_status().to_text())


def _privileged_executor_install_plan(args: Any) -> int:
    del args
    return _print(privileged_executor_install_command())


def _gui_overview(args: Any) -> int:
    return _print(gui_first_runtime_overview_to_text(profile_id=args.profile, developer=bool(args.gui_first_developer)))


ACTION_HANDLERS: dict[str, ActionHandler] = {
    "runtime.contracts.show": _runtime_contracts_show,
    "runtime.contracts.validate": _runtime_contracts_validate,
    "runtime.plan.start": _runtime_plan("start"),
    "runtime.plan.stop": _runtime_plan("stop"),
    "runtime.plan.status": _runtime_plan("status"),
    "runtime.logs.show": _runtime_log,
    "runtime.logs.snapshot": _runtime_logs,
    "runtime.owner-rules.plan.apply": _owner_rules_plan("apply"),
    "runtime.owner-rules.plan.revert": _owner_rules_plan("revert"),
    "runtime.owner-rules.apply": _owner_rules_execute("apply"),
    "runtime.owner-rules.revert": _owner_rules_execute("revert"),
    "runtime.owner-rules.reconcile": _owner_rules_reconcile,
    "runtime.session.start": _runtime_session_start,
    "runtime.session.status": _runtime_session_status,
    "runtime.session.stop": _runtime_session_stop,
    "runtime.nft-state.show": _runtime_nft_state,
    "runtime.kernel.status": _runtime_kernel_status,
    "default.build.dependencies.inspect": _default_build_deps,
    "default.build.plan": _default_build_plan,
    "default.build.apply": _default_build,
    "default.workflow.plan.start": _default_workflow_plan("start"),
    "default.workflow.plan.stop": _default_workflow_plan("stop"),
    "default.workflow.start": _default_workflow_execute("start", "started"),
    "default.workflow.status": _default_status,
    "default.workflow.stop": _default_workflow_execute("stop", "stopped"),
    "privileged.executor.status": _privileged_executor_status,
    "privileged.executor.install-plan": _privileged_executor_install_plan,
    "gui.overview.show": _gui_overview,
}


def dispatcher_validation_errors() -> tuple[str, ...]:
    errors: list[str] = []
    contract_handler_ids = {contract.handler_id for contract in P04C_ACTION_CONTRACTS if contract.handler_id}
    handler_ids = set(ACTION_HANDLERS)
    missing = sorted(contract_handler_ids - handler_ids)
    extra = sorted(handler_ids - contract_handler_ids)
    if missing:
        errors.append("contracts without executable handlers: " + ", ".join(missing))
    if extra:
        errors.append("handlers without ActionContracts: " + ", ".join(extra))
    return tuple(errors)


def dispatch_action(action_id: str, args: Any) -> int:
    """Execute exactly one canonical action.

    Selector contradiction resolution must have happened before this call. The
    dispatcher only accepts IDs present in the ActionContract catalog and binds
    them through each contract's ``handler_id``.
    """

    contract = ACTION_CONTRACT_BY_ID.get(action_id)
    if contract is None:
        print(f"Unknown ActionContract: {action_id}", file=sys.stderr)
        return 2
    handler_id = contract.handler_id or ""
    handler = ACTION_HANDLERS.get(handler_id)
    if handler is None:
        print(f"ActionContract has no executable handler: {action_id}", file=sys.stderr)
        return 2
    try:
        return int(handler(args))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
