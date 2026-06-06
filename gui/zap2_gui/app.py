"""CLI-visible entry point and optional PyQt GUI launcher."""

from __future__ import annotations

import argparse
import sys

from . import PRODUCT_LABEL
from .adapters.local_build import create_local_build_plan
from .adapters.runtime_contracts import (
    runtime_contracts_to_text,
    validate_runtime_contract_catalog,
    validate_runtime_contracts_to_text,
)
from .adapters.runtime_plan_generator import (
    SUPPORTED_RUNTIME_PLAN_ACTIONS,
    runtime_plan_to_text,
)
from .adapters.runtime_apply import (
    execute_runtime_owner_rules,
    prepare_runtime_owner_rules_plan,
    runtime_apply_plan_to_text,
)
from .adapters.runtime_state import (
    confirm_runtime_plan,
    prepare_runtime_plan,
    runtime_log_to_text,
    runtime_state_to_text,
)
from .adapters.runtime_session import (
    runtime_session_status,
    start_runtime_session,
    stop_runtime_session,
)
from .adapters.runtime_service import (
    SUPPORTED_SERVICE_EXECUTION_ACTIONS,
    SUPPORTED_SERVICE_PLAN_ACTIONS,
    create_service_plan,
    execute_service_plan,
    prepare_service_plan,
)
from .adapters.workspace_profiles import (
    workspace_profile_to_text,
    workspace_profiles_to_text,
    workspace_strategies_to_text,
    workspace_strategy_to_text,
    load_workspace_catalog,
)
from .core_inventory import load_core_build_map, load_core_inventory, load_core_inventory_snapshot
from .models.navigation import default_navigation_sections
from .project_paths import discover_layout
from .qt_compat import PyQtUnavailableError, is_pyqt_available


def describe_project() -> str:
    layout = discover_layout()
    inventory = load_core_inventory(layout.root)
    snapshot = load_core_inventory_snapshot(layout.root)
    build_map = load_core_build_map(layout.root)
    units = ", ".join(unit.name for unit in build_map.units)
    sections = ", ".join(section.title for section in default_navigation_sections())
    pyqt_state = "available" if is_pyqt_available() else "not installed"
    build_plan = create_local_build_plan(layout.root)
    workspace_catalog = load_workspace_catalog(layout.root)
    runtime_contract_issues = validate_runtime_contract_catalog(layout.root)
    runtime_contract_status = "OK" if not any(issue.severity == "error" for issue in runtime_contract_issues) else "FAILED"
    runtime_state_summary = runtime_state_to_text(layout.root).splitlines()[-2]
    return "\n".join(
        [
            f"Zap2 GUI Linux {PRODUCT_LABEL}",
            f"root: {layout.root}",
            f"core: {inventory.upstream_name} ({inventory.imported_files} imported files)",
            f"inventory: {snapshot.vendor_file_count} vendored files",
            f"build units: {units}",
            f"local build adapter: plan-only ({len(build_plan.expected_artifacts)} expected artifacts)",
            f"workspace profiles: {len(workspace_catalog.profiles)}; strategies: {len(workspace_catalog.strategies)}",
            f"runtime lifecycle contracts: {runtime_contract_status}",
            f"runtime session runner: Stage 11 ({runtime_state_summary})",
            "runtime apply/revert: Stage 12 owner-confirmed nftables plans",
            "runtime service plans: Stage 13 systemd service mode (not default)",
            f"gui shell: PyQt skeleton ({pyqt_state})",
            f"navigation: {sections}",
            "status: bootstrap/read-only baseline with optional GUI launch",
        ]
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Zap2 GUI Linux bootstrap shell")
    parser.add_argument(
        "--gui",
        action="store_true",
        help="запустить локальную PyQt GUI shell; требует установленный PyQt6 и display server",
    )
    parser.add_argument(
        "--build-plan",
        action="store_true",
        help="показать явный local build plan для ядра без запуска make",
    )
    parser.add_argument(
        "--build-target",
        default="all",
        help="цель для --build-plan: all, nfqws2, ip2net, mdig или clean",
    )


    parser.add_argument(
        "--runtime-contracts",
        action="store_true",
        help="показать runtime lifecycle contracts Stage 8 без исполнения",
    )
    parser.add_argument(
        "--runtime-plan",
        choices=SUPPORTED_RUNTIME_PLAN_ACTIONS,
        metavar="ACTION",
        help="сгенерировать default strategy runtime plan: start, stop или status; без исполнения",
    )
    parser.add_argument(
        "--profile",
        default="default",
        help="workspace-профиль для --runtime-plan; по умолчанию default",
    )
    parser.add_argument(
        "--validate-runtime-contracts",
        action="store_true",
        help="валидировать runtime lifecycle contracts Stage 8 без исполнения",
    )

    parser.add_argument(
        "--runtime-prepare",
        choices=SUPPORTED_RUNTIME_PLAN_ACTIONS,
        metavar="ACTION",
        help="сохранить runtime plan в .zap2/runtime, записать rollback notes и log; без исполнения",
    )
    parser.add_argument(
        "--runtime-confirm",
        metavar="PLAN_ID",
        help="создать owner confirmation для сохранённого plan id; без исполнения",
    )
    parser.add_argument(
        "--runtime-log",
        action="store_true",
        help="показать локальный runtime log из .zap2/runtime/logs без исправлений и исполнения",
    )


    parser.add_argument(
        "--runtime-apply-plan",
        action="store_true",
        help="подготовить owner-confirmed nftables apply plan; без исполнения",
    )
    parser.add_argument(
        "--runtime-revert-plan",
        action="store_true",
        help="подготовить owner-confirmed nftables revert plan; без исполнения",
    )
    parser.add_argument(
        "--runtime-apply",
        action="store_true",
        help="исполнить подтверждённый owner-rules apply plan; требует sudo локально",
    )
    parser.add_argument(
        "--runtime-revert",
        action="store_true",
        help="исполнить подтверждённый owner-rules revert plan; требует sudo локально",
    )
    parser.add_argument(
        "--confirm",
        metavar="PLAN_ID",
        help="plan id для owner-confirmed apply/revert execution",
    )

    parser.add_argument(
        "--runtime-session-start",
        action="store_true",
        help="запустить confirmed nfqws2 runtime session без firewall/systemd/service mutation",
    )
    parser.add_argument(
        "--runtime-session-status",
        action="store_true",
        help="показать read-only статус nfqws2 runtime session",
    )
    parser.add_argument(
        "--runtime-session-stop",
        action="store_true",
        help="остановить только PID, записанный нашим runtime session state",
    )

    parser.add_argument(
        "--service-plan",
        choices=SUPPORTED_SERVICE_PLAN_ACTIONS,
        metavar="ACTION",
        help="подготовить service plan install/start/stop/remove в .zap2/runtime; без исполнения",
    )
    parser.add_argument(
        "--service-apply",
        choices=SUPPORTED_SERVICE_EXECUTION_ACTIONS,
        metavar="ACTION",
        help="исполнить подтверждённый service install/remove plan; требует sudo для /etc/systemd/system",
    )

    parser.add_argument(
        "--list-profiles",
        action="store_true",
        help="показать workspace-профили без применения настроек",
    )
    parser.add_argument(
        "--show-profile",
        metavar="PROFILE_ID",
        help="показать один workspace-профиль без применения настроек",
    )
    parser.add_argument(
        "--list-strategies",
        action="store_true",
        help="показать каталог стратегий без исполнения",
    )
    parser.add_argument(
        "--show-strategy",
        metavar="STRATEGY_ID",
        help="показать одну стратегию без исполнения",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.gui:
        try:
            from .qt_app import run_gui

            return run_gui(sys.argv if argv is None else [sys.argv[0], *argv])
        except PyQtUnavailableError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    if args.build_plan:
        try:
            print(create_local_build_plan(target=args.build_target).to_text())
            return 0
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2


    if args.runtime_contracts:
        print(runtime_contracts_to_text())
        return 0

    if args.runtime_plan:
        try:
            print(runtime_plan_to_text(action=args.runtime_plan, profile_id=args.profile))
            return 0
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    if args.validate_runtime_contracts:
        text = validate_runtime_contracts_to_text()
        print(text)
        return 0 if "FAILED" not in text else 1

    if args.runtime_prepare:
        try:
            print(prepare_runtime_plan(action=args.runtime_prepare, profile_id=args.profile).to_text())
            return 0
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    if args.runtime_confirm:
        try:
            print(confirm_runtime_plan(plan_id=args.runtime_confirm).to_text())
            return 0
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    if args.runtime_log:
        print(runtime_log_to_text(profile_id=args.profile))
        return 0


    if args.runtime_apply_plan:
        try:
            prepared = prepare_runtime_owner_rules_plan(action="apply", profile_id=args.profile)
            print(prepared.to_text())
            return 0
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    if args.runtime_revert_plan:
        try:
            prepared = prepare_runtime_owner_rules_plan(action="revert", profile_id=args.profile)
            print(prepared.to_text())
            return 0
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    if args.runtime_apply:
        try:
            print(execute_runtime_owner_rules(action="apply", profile_id=args.profile, confirm_plan_id=args.confirm or "").to_text())
            return 0
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    if args.runtime_revert:
        try:
            print(execute_runtime_owner_rules(action="revert", profile_id=args.profile, confirm_plan_id=args.confirm or "").to_text())
            return 0
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    if args.runtime_session_start:
        try:
            print(start_runtime_session(profile_id=args.profile).to_text())
            return 0
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    if args.runtime_session_status:
        try:
            print(runtime_session_status(profile_id=args.profile).to_text())
            return 0
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    if args.runtime_session_stop:
        try:
            print(stop_runtime_session(profile_id=args.profile).to_text())
            return 0
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2


    if args.service_plan:
        try:
            prepared = prepare_service_plan(action=args.service_plan, profile_id=args.profile)
            plan_text = create_service_plan(action=args.service_plan, profile_id=args.profile).to_text()
            print(plan_text)
            print()
            print(prepared.to_text())
            return 0
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    if args.service_apply:
        try:
            print(execute_service_plan(action=args.service_apply, profile_id=args.profile, confirm_plan_id=args.confirm or "").to_text())
            return 0
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    if args.list_profiles:
        print(workspace_profiles_to_text())
        return 0

    if args.show_profile:
        try:
            print(workspace_profile_to_text(args.show_profile))
            return 0
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    if args.list_strategies:
        print(workspace_strategies_to_text())
        return 0

    if args.show_strategy:
        try:
            print(workspace_strategy_to_text(args.show_strategy))
            return 0
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    print(describe_project())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
