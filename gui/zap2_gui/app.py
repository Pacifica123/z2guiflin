"""CLI-visible entry point and optional PyQt GUI launcher."""

from __future__ import annotations

import argparse
import sys

from . import PRODUCT_LABEL
from .adapters.blockcheck_gui import (
    SUPPORTED_BLOCKCHECK_DEAD_TARGET_GUARDS,
    SUPPORTED_BLOCKCHECK_IPVS,
    SUPPORTED_BLOCKCHECK_SCANLEVELS,
    SUPPORTED_BLOCKCHECK_SCAN_MODES,
    SUPPORTED_BLOCKCHECK_TESTS,
    BLOCKCHECK_DEAD_TARGET_GUARD_AUTO_STOP,
    BLOCKCHECK_DEAD_TARGET_GUARD_OBSERVE_ONLY,
    BLOCKCHECK_SCAN_ALL_TARGETS,
    BLOCKCHECK_SCAN_STOP_AFTER_FIRST_AVAILABLE,
    BlockcheckOptions,
    blockcheck_build_plan_to_text,
    blockcheck_coverage_to_text,
    blockcheck_service_policy_to_text,
    blockcheck_tournament_to_text,
    blockcheck_strategy_validation_plan_to_text,
    blockcheck_plan_to_text,
    blockcheck_preflight_to_text,
    execute_blockcheck_prereq_build,
    execute_blockcheck_with_gui_sudo,
    export_blockcheck_available_strategies,
    last_blockcheck_log_to_text,
)
from .adapters.build_dependencies import run_build_dependency_preflight
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
from .adapters.runtime_logs import runtime_log_snapshot_to_text
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
from .adapters.runtime_default import (
    SUPPORTED_DEFAULT_WORKFLOW_ACTIONS,
    execute_default_workflow,
    prepare_default_workflow_plan,
    default_workflow_status,
)
from .adapters.runtime_default_build import (
    execute_default_build,
    prepare_default_build_plan,
)
from .adapters.gui_privilege import (
    SUPPORTED_GUI_PRIVILEGED_ACTIONS,
    gui_privileged_command_to_text,
)
from .adapters.discord_verification import (
    discord_non_voice_verification_plan_to_text,
    write_discord_non_voice_report_template_to_text,
)
from .adapters.discord_endpoint_discovery import (
    DEFAULT_DISCOVERY_SECONDS,
    discord_endpoint_discovery_plan_to_text,
    discord_endpoint_report_to_text,
    discord_endpoint_watch_to_text,
    discord_netlog_plan_to_text,
)
from .adapters.workspace_profiles import (
    workspace_profile_to_text,
    workspace_profiles_to_text,
    workspace_strategies_to_text,
    workspace_strategy_to_text,
    load_workspace_catalog,
    select_workspace_strategy,
)
from .core_inventory import load_core_build_map, load_core_inventory, load_core_inventory_snapshot
from .models.navigation import default_navigation_sections
from .models.service_targets import (
    DEFAULT_SERVICE_TARGET_PRESET_ID,
    SERVICE_TARGET_CUSTOM,
    SERVICE_TARGET_DISCORD_DESKTOP,
    get_service_target_preset,
    list_service_target_presets,
    service_target_recommended_scan_mode,
    service_target_string,
)
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
            "default build workflow: v0.4-alpha over v0.3-stable baseline owner-confirmed local make",
            "default workflow: Stage 14 owner-confirmed start/stop",
            "GUI privileged start/stop: v0.4-alpha via graphical sudo askpass",
            "blockcheck lab: v0.4-alpha service targets plus Discord endpoint discovery diagnostics",
            f"gui shell: PyQt skeleton ({pyqt_state})",
            f"navigation: {sections}",
            "status: v0.4-alpha documentation baseline; next cycle targets desktop Discord",
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
        "--runtime-logs",
        action="store_true",
        help="показать агрегированные runtime logs/stderr/stdout/debug tail для GUI и CLI; без исполнения",
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
        "--default-build-deps",
        action="store_true",
        help="проверить build dependencies для default build target; без установки пакетов и без make",
    )
    parser.add_argument(
        "--default-build-plan",
        action="store_true",
        help="подготовить owner-confirmed local build plan для build target default profile; без запуска make",
    )
    parser.add_argument(
        "--default-build",
        action="store_true",
        help="исполнить подтверждённую локальную сборку build target default profile; без sudo/firewall/service",
    )

    parser.add_argument(
        "--default-start-plan",
        action="store_true",
        help="подготовить composite plan запуска default strategy; без исполнения",
    )
    parser.add_argument(
        "--default-stop-plan",
        action="store_true",
        help="подготовить composite plan отключения default strategy; без исполнения",
    )
    parser.add_argument(
        "--default-start",
        action="store_true",
        help="исполнить подтверждённый default start workflow: apply owner-rules + session start",
    )
    parser.add_argument(
        "--default-stop",
        action="store_true",
        help="исполнить подтверждённый default stop workflow: session stop + revert owner-rules",
    )
    parser.add_argument(
        "--default-status",
        action="store_true",
        help="показать read-only статус default workflow/session для GUI и CLI",
    )
    parser.add_argument(
        "--gui-privileged-command",
        choices=SUPPORTED_GUI_PRIVILEGED_ACTIONS,
        metavar="ACTION",
        help="показать sudo-askpass команду, которую GUI использует для default start/stop; без исполнения",
    )

    parser.add_argument(
        "--blockcheck-preflight",
        action="store_true",
        help="показать read-only preflight для GUI blockcheck lab",
    )
    parser.add_argument(
        "--blockcheck-plan",
        action="store_true",
        help="показать sudo-askpass план запуска upstream blockcheck2.sh; без исполнения",
    )
    parser.add_argument(
        "--blockcheck-run",
        action="store_true",
        help="запустить upstream blockcheck2.sh через графический sudo askpass",
    )
    parser.add_argument(
        "--blockcheck-build-plan",
        action="store_true",
        help="показать local build plan для nfqws2/mdig prerequisites blockcheck; без запуска make",
    )
    parser.add_argument(
        "--blockcheck-build",
        action="store_true",
        help="собрать nfqws2/mdig prerequisites локально через make без sudo/firewall/service",
    )
    parser.add_argument(
        "--blockcheck-last-log",
        action="store_true",
        help="показать последний сохранённый GUI blockcheck log; без исполнения",
    )
    parser.add_argument(
        "--blockcheck-export-strategies",
        action="store_true",
        help="создать strategies/generated/*.json из AVAILABLE стратегий последнего blockcheck log и обновить catalog.json",
    )
    parser.add_argument(
        "--blockcheck-coverage",
        action="store_true",
        help="показать per-target coverage manifest для последнего service target preset; без исполнения",
    )
    parser.add_argument(
        "--blockcheck-service-policy",
        action="store_true",
        help="показать универсальную coverage policy для выбранного service target preset; без исполнения",
    )
    parser.add_argument(
        "--blockcheck-tournament",
        action="store_true",
        help="показать read-only service coverage tournament/best-so-far snapshot; без исполнения",
    )
    parser.add_argument(
        "--blockcheck-validate-strategy-plan",
        metavar="STRATEGY_ID",
        help="подготовить read-only план проверки одной strategy через upstream custom list на одном target из --blockcheck-domains",
    )
    parser.add_argument(
        "--select-strategy",
        metavar="STRATEGY_ID",
        help="выбрать strategy id для Default profile; только сохраняет .zap2 selection, без запуска",
    )
    parser.add_argument(
        "--discord-verification-plan",
        action="store_true",
        help="показать owner verification loop для Discord desktop non-voice; без запуска проверок",
    )
    parser.add_argument(
        "--discord-verification-template",
        action="store_true",
        help="создать markdown-шаблон owner report для Discord desktop non-voice в .zap2/verification",
    )
    parser.add_argument(
        "--discord-endpoint-plan",
        action="store_true",
        help="показать read-only план discovery для endpoints desktop Discord updater; без запуска",
    )
    parser.add_argument(
        "--discord-endpoint-watch",
        action="store_true",
        help="read-only ss/pgrep watch: запустите Discord во время окна наблюдения, чтобы увидеть TCP/UDP endpoints",
    )
    parser.add_argument(
        "--discord-endpoint-report",
        action="store_true",
        help="показать последний сохранённый Discord endpoint discovery snapshot",
    )
    parser.add_argument(
        "--discord-netlog-plan",
        action="store_true",
        help="показать privacy-aware owner plan для optional Chromium netlog диагностики Discord",
    )
    parser.add_argument(
        "--discord-endpoint-seconds",
        type=int,
        default=DEFAULT_DISCOVERY_SECONDS,
        help="длительность --discord-endpoint-watch в секундах: 1..600",
    )
    parser.add_argument(
        "--blockcheck-target-preset",
        choices=tuple(item.preset_id for item in list_service_target_presets()),
        default=DEFAULT_SERVICE_TARGET_PRESET_ID,
        help="service target preset для blockcheck: youtube-basic, discord-desktop или custom",
    )
    parser.add_argument(
        "--blockcheck-domains",
        default=None,
        help="ручные домены/URI для blockcheck; если задано, режим считается custom override",
    )
    parser.add_argument(
        "--blockcheck-scan-mode",
        choices=SUPPORTED_BLOCKCHECK_SCAN_MODES,
        default=None,
        help="candidate scan mode: для discord-desktop по умолчанию scan-all-targets, для остальных stop-after-first-available",
    )
    parser.add_argument(
        "--blockcheck-dead-target-guard",
        choices=SUPPORTED_BLOCKCHECK_DEAD_TARGET_GUARDS,
        default=None,
        help="dead-target precheck mode: auto-stop или observe-only; для discord-desktop по умолчанию observe-only",
    )
    parser.add_argument(
        "--blockcheck-test",
        choices=SUPPORTED_BLOCKCHECK_TESTS,
        default="standard",
        help="набор blockcheck2.d: standard или custom",
    )
    parser.add_argument(
        "--blockcheck-scanlevel",
        choices=SUPPORTED_BLOCKCHECK_SCANLEVELS,
        default="quick",
        help="scanlevel: quick, standard или force",
    )
    parser.add_argument(
        "--blockcheck-ipvs",
        choices=SUPPORTED_BLOCKCHECK_IPVS,
        default="4",
        help="IP версии для blockcheck: 4, 6 или 46",
    )
    parser.add_argument(
        "--blockcheck-http",
        action="store_true",
        help="включить HTTP checks; по умолчанию выключено для YouTube-oriented scan",
    )
    parser.add_argument(
        "--blockcheck-disable-tls12",
        action="store_true",
        help="выключить HTTPS TLS1.2 checks",
    )
    parser.add_argument(
        "--blockcheck-disable-tls13",
        action="store_true",
        help="выключить HTTPS TLS1.3 checks",
    )
    parser.add_argument(
        "--blockcheck-disable-http3",
        action="store_true",
        help="выключить HTTP/3 QUIC checks",
    )
    parser.add_argument(
        "--blockcheck-dnscheck",
        action="store_true",
        help="включить upstream DNS precheck; по умолчанию пропускается",
    )
    parser.add_argument(
        "--blockcheck-repeats",
        type=int,
        default=1,
        help="число повторов blockcheck на стратегию: 1..5",
    )
    parser.add_argument(
        "--blockcheck-curl-timeout",
        type=int,
        default=3,
        help="curl timeout для отдельных проб: 1..15 секунд",
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


def _blockcheck_domains_from_args(args: argparse.Namespace) -> str:
    manual_domains = (args.blockcheck_domains or "").strip()
    if manual_domains:
        return manual_domains
    preset_id = str(args.blockcheck_target_preset)
    preset = get_service_target_preset(preset_id)
    if preset.is_custom:
        raise ValueError("--blockcheck-target-preset custom требует явный --blockcheck-domains")
    return service_target_string(preset_id)


def _blockcheck_service_target_preset_id_from_args(args: argparse.Namespace) -> str:
    if (args.blockcheck_domains or "").strip():
        return SERVICE_TARGET_CUSTOM
    return str(args.blockcheck_target_preset)


def _blockcheck_scan_mode_from_args(args: argparse.Namespace) -> str:
    if args.blockcheck_scan_mode:
        return str(args.blockcheck_scan_mode)
    if not (args.blockcheck_domains or "").strip():
        return service_target_recommended_scan_mode(str(args.blockcheck_target_preset))
    return BLOCKCHECK_SCAN_STOP_AFTER_FIRST_AVAILABLE


def _blockcheck_dead_target_guard_from_args(args: argparse.Namespace) -> str:
    if args.blockcheck_dead_target_guard:
        return str(args.blockcheck_dead_target_guard)
    if not (args.blockcheck_domains or "").strip() and str(args.blockcheck_target_preset) == SERVICE_TARGET_DISCORD_DESKTOP:
        return BLOCKCHECK_DEAD_TARGET_GUARD_OBSERVE_ONLY
    return BLOCKCHECK_DEAD_TARGET_GUARD_AUTO_STOP


def _blockcheck_options_from_args(args: argparse.Namespace) -> BlockcheckOptions:
    return BlockcheckOptions(
        domains=_blockcheck_domains_from_args(args),
        service_target_preset_id=_blockcheck_service_target_preset_id_from_args(args),
        scan_mode=_blockcheck_scan_mode_from_args(args),
        test=args.blockcheck_test,
        scanlevel=args.blockcheck_scanlevel,
        ipvs=args.blockcheck_ipvs,
        enable_http=args.blockcheck_http,
        enable_https_tls12=not args.blockcheck_disable_tls12,
        enable_https_tls13=not args.blockcheck_disable_tls13,
        enable_http3=not args.blockcheck_disable_http3,
        skip_dnscheck=not args.blockcheck_dnscheck,
        repeats=args.blockcheck_repeats,
        curl_max_time=args.blockcheck_curl_timeout,
        dead_target_guard=_blockcheck_dead_target_guard_from_args(args),
    )


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


    if args.discord_verification_plan:
        print(discord_non_voice_verification_plan_to_text())
        return 0

    if args.discord_verification_template:
        print(write_discord_non_voice_report_template_to_text())
        return 0

    if args.discord_endpoint_plan:
        print(discord_endpoint_discovery_plan_to_text(seconds=args.discord_endpoint_seconds))
        return 0

    if args.discord_endpoint_watch:
        print(discord_endpoint_watch_to_text(seconds=args.discord_endpoint_seconds))
        return 0

    if args.discord_endpoint_report:
        print(discord_endpoint_report_to_text())
        return 0

    if args.discord_netlog_plan:
        print(discord_netlog_plan_to_text())
        return 0

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

    if args.runtime_logs:
        print(runtime_log_snapshot_to_text(profile_id=args.profile))
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


    if args.default_build_deps:
        print(run_build_dependency_preflight("nfqws2").to_text())
        return 0

    if args.default_build_plan:
        try:
            print(prepare_default_build_plan(profile_id=args.profile).to_text())
            return 0
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    if args.default_build:
        try:
            print(execute_default_build(profile_id=args.profile, confirm_plan_id=args.confirm or "").to_text())
            return 0
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    if args.default_start_plan:
        try:
            print(prepare_default_workflow_plan(action="start", profile_id=args.profile).to_text())
            return 0
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    if args.default_stop_plan:
        try:
            print(prepare_default_workflow_plan(action="stop", profile_id=args.profile).to_text())
            return 0
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    if args.default_start:
        try:
            result = execute_default_workflow(action="start", profile_id=args.profile, confirm_plan_id=args.confirm or "")
            print(result.to_text())
            return 0 if result.state == "started" else 1
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    if args.default_status:
        try:
            print(default_workflow_status(profile_id=args.profile).to_text())
            return 0
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    if args.gui_privileged_command:
        try:
            print(gui_privileged_command_to_text(action=args.gui_privileged_command, profile_id=args.profile))
            return 0
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    if args.default_stop:
        try:
            result = execute_default_workflow(action="stop", profile_id=args.profile, confirm_plan_id=args.confirm or "")
            print(result.to_text())
            return 0 if result.state == "stopped" else 1
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    if args.blockcheck_preflight:
        print(blockcheck_preflight_to_text())
        return 0

    if args.blockcheck_plan:
        try:
            print(blockcheck_plan_to_text(options=_blockcheck_options_from_args(args)))
            return 0
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    if args.blockcheck_build_plan:
        try:
            print(blockcheck_build_plan_to_text())
            return 0
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    if args.blockcheck_build:
        try:
            result = execute_blockcheck_prereq_build()
            print(result.to_text())
            return 0 if result.ok else 1
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    if args.blockcheck_run:
        try:
            result = execute_blockcheck_with_gui_sudo(options=_blockcheck_options_from_args(args))
            print(result.to_text())
            return 0 if result.ok else 1
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    if args.blockcheck_last_log:
        print(last_blockcheck_log_to_text())
        return 0

    if args.blockcheck_coverage:
        print(blockcheck_coverage_to_text())
        return 0

    if args.blockcheck_service_policy:
        try:
            print(blockcheck_service_policy_to_text(str(args.blockcheck_target_preset)))
            return 0
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    if args.blockcheck_tournament:
        try:
            print(blockcheck_tournament_to_text(preset_id=str(args.blockcheck_target_preset)))
            return 0
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    if args.blockcheck_validate_strategy_plan:
        try:
            target = _blockcheck_domains_from_args(args).split()[0]
            print(blockcheck_strategy_validation_plan_to_text(strategy_id=str(args.blockcheck_validate_strategy_plan), target=target))
            return 0
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    if args.blockcheck_export_strategies:
        try:
            result = export_blockcheck_available_strategies()
            print(result.to_text())
            return 0 if result.ok else 1
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    if args.select_strategy:
        try:
            print(select_workspace_strategy(strategy_id=args.select_strategy, profile_id=args.profile).to_text())
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
