"""CLI-visible entry point and optional PyQt GUI launcher."""

from __future__ import annotations

import argparse
import json
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
    reconcile_runtime_owner_rules,
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
from .adapters.runtime_nft_state import runtime_nft_state_to_text, runtime_pretls_probe_to_text
from .adapters.gui_first_overview import gui_first_runtime_overview_to_text
from .adapters.discord_pretls_guided_probe import (
    DEFAULT_GUIDED_PROBE_WAIT_SECONDS,
    runtime_discord_pretls_guided_probe_to_text,
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
from .adapters.privileged_executor import (
    execute_bounded_default_workflow,
    execute_bounded_owner_rules,
    execute_bounded_session_start,
    privileged_executor_install_command,
    privileged_executor_status,
)
from .adapters.runtime_kernel import runtime_kernel_status
from .adapters.runtime_migration import migrate_runtime_session_state
from .adapters.launch_composer import (
    KNOWN_LAUNCH_COMPONENTS,
    launch_composer_plan_to_text,
    launch_composer_start_to_text,
    launch_composer_status_to_text,
    launch_composer_stop_to_text,
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
from .adapters.discord_har_discovery import (
    discord_har_analyze_to_text,
    discord_har_plan_to_text,
    discord_har_report_to_text,
)
from .adapters.discord_har_workbench import (
    discord_har_group_plan_to_text,
    discord_har_workbench_report_to_text,
    discord_har_workbench_to_text,
)
from .adapters.har_discovery import (
    har_analyze_to_text,
    har_plan_to_text,
    har_report_to_text,
)
from .adapters.har_workbench import (
    har_group_plan_to_text,
    har_workbench_report_to_text,
    har_workbench_to_text,
)
from .adapters.discord_voice_profiles import discord_voice_profiles_to_text
from .adapters.discord_dns_edge_diagnostics import (
    DEFAULT_DNS_EDGE_RESOLVERS,
    discord_dns_edge_check_to_text,
    discord_dns_edge_plan_to_text,
)
from .adapters.external_reference_audit import external_reference_audit_to_text
from .adapters.discord_observation_matrix import (
    DEFAULT_MATRIX_ROW_SECONDS,
    discord_observation_matrix_plan_to_text,
    discord_observation_matrix_report_to_text,
    discord_observation_matrix_run_row_to_text,
)
from .adapters.discord_tunnel import (
    SUPPORTED_CORE_KINDS,
    SUPPORTED_LAUNCH_MODES,
    DEFAULT_SOCKS_PORT,
    DEFAULT_TUNNEL_HTTPS_HOST,
    DEFAULT_TUNNEL_HTTPS_PATH,
    DEFAULT_TUNNEL_OBSERVE_SECONDS,
    SUPPORTED_UPDATER_RESULTS,
    discord_launch_through_socks_to_text,
    discord_proxy_route_plan_to_text,
    discord_stop_launched_to_text,
    discord_tunnel_guided_run_to_text,
    discord_tunnel_https_probe_to_text,
    discord_tunnel_core_preflight_to_text,
    discord_tunnel_evidence_to_text,
    discord_tunnel_plan_to_text,
    discord_tunnel_probe_to_text,
    discord_tunnel_route_diagnose_to_text,
    discord_tunnel_start_to_text,
    discord_tunnel_status_to_text,
    discord_tunnel_stop_to_text,
    discord_tunnel_tun_plan_to_text,
    select_tunnel_connection,
    tunnel_connection_import_vless_to_text,
    tunnel_connections_to_text,
)
from .adapters.strategy_parser_preflight import strategy_parser_preflight_to_text
from .adapters.security_blocklist import (
    apply_security_blocklist,
    install_security_blocklist_timer,
    refresh_security_blocklist,
    remove_security_blocklist,
    remove_security_blocklist_timer,
    security_blocklist_status,
    security_blocklist_timer_plan,
    set_security_blocklist_enabled,
    update_security_blocklist,
)
from .adapters.tor_backends import (
    DEFAULT_TOR_BACKEND,
    DEFAULT_TOR_SOCKS_PORT,
    SUPPORTED_TOR_BACKENDS,
    tor_backend_plan_to_text,
    tor_backend_start_to_text,
    tor_backend_status_to_text,
    tor_backend_stop_to_text,
)
from .adapters.presets import (
    load_preset_catalog,
    preset_catalog_to_text,
    preset_profile_to_text,
    preset_to_text,
    select_preset,
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
    preset_catalog = load_preset_catalog(layout.root)
    runtime_contract_issues = validate_runtime_contract_catalog(layout.root)
    runtime_contract_status = "OK" if not any(issue.severity == "error" for issue in runtime_contract_issues) else "FAILED"
    runtime_state_summary = runtime_state_to_text(layout.root).splitlines()[-2]
    return "\n".join(
        [
            f"Zap2 GUI Linux {PRODUCT_LABEL}",
            f"root: {layout.root}",
            f"core: {inventory.upstream_name} ({inventory.imported_files} imported files)",
            f"inventory: {snapshot.vendor_file_count} core files ({snapshot.project_local_core_file_count} project-local)",
            f"build units: {units}",
            f"local build adapter: plan-only ({len(build_plan.expected_artifacts)} expected artifacts)",
            f"workspace contexts: {len(workspace_catalog.profiles)}; presets: {len(preset_catalog.entries)}; traffic profiles: {preset_catalog.profile_count}",
            f"runtime lifecycle contracts: {runtime_contract_status}",
            f"runtime session runner: Stage 11 ({runtime_state_summary})",
            "runtime apply/revert: Stage 12 owner-confirmed nftables plans",
            "runtime service plans: Stage 13 systemd service mode (not default)",
            "default build workflow: v0.4 owner-confirmed local make over the v0.3-stable baseline",
            "default workflow: Stage 14 owner-confirmed start/stop",
            "GUI privileged start/stop: v0.4 via graphical sudo askpass",
            "blockcheck lab: v0.4 universal HAR workbench, service targets and separate Discord Voice profiles",
            "discord tunnel lane: Stage 7y SOCKS/VLESS guided experiment with GUI clipboard import",
            "launch composer: Stage 7z GUI panel for combining Zapret and tunnel components",
            f"gui shell: PyQt skeleton ({pyqt_state})",
            f"navigation: {sections}",
            "status: v0.4 working diagnostic/runtime platform; strategy results remain environment-dependent",
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

    parser.add_argument("--security-blocklist-status", action="store_true", help="показать config/cache state security IP blocklist без сетевых изменений")
    parser.add_argument("--security-blocklist-enable", action="store_true", help="включить outbound security blocklist policy в локальном config; apply отдельно")
    parser.add_argument("--security-blocklist-enable-inbound", action="store_true", help="включить также inbound blocking (host-wide INPUT); требует осознанного выбора")
    parser.add_argument("--security-blocklist-disable", action="store_true", help="выключить policy в config и удалить только owned nft table")
    parser.add_argument("--security-blocklist-update", action="store_true", help="скачать/валидировать external lists и атомарно заменить last-known-good cache; firewall не меняется")
    parser.add_argument("--security-blocklist-apply", action="store_true", help="применить validated cache в isolated owned nft table; требует root")
    parser.add_argument("--security-blocklist-refresh", action="store_true", help="periodic path: update с LKG fallback + apply; требует root")
    parser.add_argument("--security-blocklist-timer-plan", action="store_true", help="показать systemd service/timer для 2h periodic refresh; без установки")
    parser.add_argument("--security-blocklist-install-timer", action="store_true", help="установить workspace-scoped systemd timer; требует root")
    parser.add_argument("--security-blocklist-remove-timer", action="store_true", help="удалить только workspace-scoped blocklist timer; firewall не меняет")


    parser.add_argument(
        "--strategy-parser-preflight",
        action="store_true",
        help="Stage 8h: выполнить read-only nfqws2 --dry-run для выбранной workspace strategy",
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
        help="workspace context для runtime-команд; по умолчанию default",
    )

    parser.add_argument(
        "--launch-components",
        default="zapret-default",
        help="компоненты для launch composer через запятую: " + ",".join(KNOWN_LAUNCH_COMPONENTS),
    )
    parser.add_argument(
        "--launch-composer-plan",
        action="store_true",
        help="Stage 7z: показать read-only план комбинированного запуска выбранных компонентов",
    )
    parser.add_argument(
        "--launch-composer-status",
        action="store_true",
        help="Stage 7z: показать read-only статус launch composer и всех launch components",
    )
    parser.add_argument(
        "--launch-composer-start",
        action="store_true",
        help="Stage 7z: запустить выбранные supported components в порядке composer; Zapret требует GUI sudo-askpass",
    )
    parser.add_argument(
        "--launch-composer-stop",
        action="store_true",
        help="Stage 7z: остановить выбранные supported components в обратном порядке composer",
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
        "--runtime-reconcile",
        action="store_true",
        help="read-only reconcile saved owner state с observed nft table; unknown/conflict не удаляются автоматически",
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
        "--runtime-nft-state",
        action="store_true",
        help="показать read-only nft/NFQUEUE capture snapshot и manual counter command; без исполнения nft",
    )
    parser.add_argument(
        "--runtime-pretls-probe",
        action="store_true",
        help="показать read-only pre-TLS probe checklist для активного nfqws2/nft состояния; без исполнения nft",
    )
    parser.add_argument(
        "--runtime-discord-pretls-guided-probe",
        action="store_true",
        help="интерактивный guided-прогон Discord pre-TLS: counters before/after, nfqws2 health, verdict report; без запуска Discord и без firewall mutation",
    )
    parser.add_argument(
        "--discord-observation-matrix-plan",
        action="store_true",
        help="показать Stage 7o2 matrix-plan: baseline, diagnostic, current v2 и external-reference кандидаты; без исполнения",
    )
    parser.add_argument(
        "--discord-observation-matrix-report",
        action="store_true",
        help="собрать read-only Stage 7o2 observation matrix из уже сохранённых guided reports/snapshots",
    )
    parser.add_argument(
        "--discord-observation-matrix-run-row",
        metavar="ROW_ID",
        help="Stage 7o2a: упростить сбор одной строки observation matrix: baseline или guided row runner",
    )
    parser.add_argument(
        "--matrix-row-wait-seconds",
        type=int,
        default=DEFAULT_MATRIX_ROW_SECONDS,
        help="окно наблюдения для --discord-observation-matrix-run-row: 0..600 секунд",
    )
    parser.add_argument(
        "--matrix-row-no-wait",
        action="store_true",
        help="не ждать Enter/manual action в matrix row runner; полезно для dry-run/CI",
    )
    parser.add_argument(
        "--matrix-row-auto",
        action="store_true",
        help="Stage 7o2d: максимально автоматизировать строку матрицы: auto-build/confirm/prepare, а в sudo-фазе auto-start + guided probe",
    )

    parser.add_argument(
        "--tunnel-connection-import-vless",
        metavar="URI_OR_@FILE",
        help="Stage 7p1: импортировать VLESS share link в .zap2/tunnel и auto-select; секрет не печатается",
    )
    parser.add_argument(
        "--tunnel-connections",
        action="store_true",
        help="Stage 7p1: показать redacted список Discord tunnel connection profiles; без запуска",
    )
    parser.add_argument(
        "--tunnel-select-connection",
        metavar="CONNECTION_ID",
        help="Stage 7p1: выбрать активный tunnel connection profile; без запуска",
    )
    parser.add_argument(
        "--tunnel-core-binary",
        default=None,
        help="путь к внешнему core binary (xray/v2ray/sing-box) для --discord-tunnel-plan",
    )
    parser.add_argument(
        "--tunnel-core-kind",
        choices=SUPPORTED_CORE_KINDS,
        default="auto",
        help="тип внешнего core для argv generation: auto, xray, v2ray или sing-box",
    )
    parser.add_argument(
        "--tunnel-socks-port",
        type=int,
        default=DEFAULT_SOCKS_PORT,
        help="локальный loopback SOCKS port для tunnel lane; по умолчанию 10808",
    )
    parser.add_argument("--tor-backend", choices=SUPPORTED_TOR_BACKENDS, default=DEFAULT_TOR_BACKEND, help="Tor backend: системный C Tor или отдельный Arti")
    parser.add_argument("--tor-binary", default=None, help="явный путь к tor/arti binary")
    parser.add_argument("--tor-socks-port", type=int, default=DEFAULT_TOR_SOCKS_PORT, help="loopback SOCKS port Tor backend")
    parser.add_argument("--tor-backend-plan", action="store_true", help="подготовить owner-confirmed plan запуска C Tor/Arti")
    parser.add_argument("--tor-backend-start", action="store_true", help="запустить C Tor/Arti по confirmed plan")
    parser.add_argument("--tor-backend-status", action="store_true", help="read-only статус managed Tor backend")
    parser.add_argument("--tor-backend-stop", action="store_true", help="остановить только PID managed Tor backend")

    parser.add_argument(
        "--discord-tunnel-plan",
        action="store_true",
        help="Stage 7p2: подготовить owner-confirmed Discord SOCKS/VLESS tunnel start plan и redacted core config preview",
    )
    parser.add_argument(
        "--discord-tunnel-core-preflight",
        action="store_true",
        help="Stage 8h: проверить generated Xray VLESS config через upstream `xray run -test`; без persistent start",
    )
    parser.add_argument(
        "--discord-tunnel-start",
        action="store_true",
        help="Stage 7p3: запустить внешний core по confirmed tunnel plan; без sudo/firewall/service",
    )
    parser.add_argument(
        "--tunnel-allow-zapret-parallel",
        action="store_true",
        help="разрешить tunnel start при уже running default zapret workflow; только для explicit launch composer experiments",
    )
    parser.add_argument(
        "--discord-tunnel-stop",
        action="store_true",
        help="Stage 7p3: остановить только managed tunnel core PID из .zap2/tunnel/runtime",
    )
    parser.add_argument(
        "--discord-tunnel-status",
        action="store_true",
        help="Stage 7p3: read-only статус managed tunnel core/session",
    )
    parser.add_argument(
        "--discord-tunnel-probe",
        action="store_true",
        help="Stage 7p3: проверить running core и loopback SOCKS port; без запуска Discord",
    )
    parser.add_argument(
        "--discord-tunnel-https-probe",
        action="store_true",
        help="Stage 7p5: выполнить harmless HTTPS HEAD через managed local SOCKS; без запуска Discord",
    )
    parser.add_argument(
        "--discord-tunnel-route-diagnose",
        action="store_true",
        help="Stage 8c: свести tunnel/SOCKS/upstream/Discord logs в короткий route verdict; read-only",
    )
    parser.add_argument(
        "--discord-tunnel-evidence",
        action="store_true",
        help="P01: показать current-run EvidenceGraph и CapabilityVerdict без вывода секретов; read-only",
    )
    parser.add_argument(
        "--tunnel-probe-host",
        default=DEFAULT_TUNNEL_HTTPS_HOST,
        help="host для --discord-tunnel-https-probe; по умолчанию updates.discord.com",
    )
    parser.add_argument(
        "--tunnel-probe-path",
        default=DEFAULT_TUNNEL_HTTPS_PATH,
        help="path для --discord-tunnel-https-probe; по умолчанию /",
    )
    parser.add_argument(
        "--tunnel-probe-timeout",
        type=float,
        default=8.0,
        help="timeout секунд для SOCKS/HTTPS probe; 1..60",
    )
    parser.add_argument(
        "--discord-tunnel-guided-run",
        action="store_true",
        help="Stage 7p5: one-command owner guided SOCKS/VLESS run: plan+confirm+start+probe+launch+verdict",
    )
    parser.add_argument(
        "--tunnel-guided-no-wait",
        action="store_true",
        help="не ждать observation/manual verdict в --discord-tunnel-guided-run; полезно для dry-run/CI",
    )
    parser.add_argument(
        "--tunnel-observe-seconds",
        type=int,
        default=DEFAULT_TUNNEL_OBSERVE_SECONDS,
        help="сколько секунд ждать перед updater verdict prompt в guided tunnel run; 0..600",
    )
    parser.add_argument(
        "--discord-updater-result",
        choices=SUPPORTED_UPDATER_RESULTS,
        default="unknown",
        help="owner-observed updater result для guided tunnel report: passed, stuck, unknown",
    )
    parser.add_argument(
        "--discord-tunnel-tun-plan",
        action="store_true",
        help="Stage 7p5: plan-only TUN/TProxy research lane; ничего не применяет",
    )
    parser.add_argument(
        "--discord-proxy-route-plan",
        action="store_true",
        help="Stage 8a: объяснить, как направить Discord/браузер через managed local SOCKS; без запуска",
    )
    parser.add_argument(
        "--discord-launch-through-socks",
        action="store_true",
        help="Stage 7p4/8a: запустить Discord command с SOCKS env/Chromium proxy candidates через active tunnel",
    )
    parser.add_argument(
        "--discord-launch-preflight",
        action="store_true",
        help="Stage 8c: перед запуском Discord проверить HTTPS через SOCKS; при провале launch блокируется",
    )
    parser.add_argument(
        "--discord-launch-allow-failed-preflight",
        action="store_true",
        help="Stage 8c: разрешить ручной launch даже если --discord-launch-preflight failed",
    )
    parser.add_argument(
        "--discord-stop-launched",
        action="store_true",
        help="Stage 8b: остановить Discord process group, запущенный через --discord-launch-through-socks",
    )
    parser.add_argument(
        "--discord-binary",
        default="auto",
        help="Discord/Vesktop command; auto предпочитает Vesktop, затем Discord. Примеры: vesktop, 'flatpak run dev.vencord.Vesktop', discord",
    )
    parser.add_argument(
        "--discord-launch-mode",
        choices=SUPPORTED_LAUNCH_MODES,
        default="socks-updater-window",
        help="режим запуска Discord через SOCKS: updater-window, full-session, env-only или flag-only",
    )
    parser.add_argument(
        "--pretls-probe-wait-seconds",
        type=int,
        default=DEFAULT_GUIDED_PROBE_WAIT_SECONDS,
        help="ожидание для --runtime-discord-pretls-guided-probe в non-interactive режиме: 0..600 секунд",
    )
    parser.add_argument(
        "--pretls-probe-no-wait",
        action="store_true",
        help="не ждать Enter/manual action в guided-probe; полезно для CI и dry-run проверки состояния",
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
        help="P02 plan-only: privileged service execution staged/unsupported; используйте --service-plan для review",
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
        "--runtime-kernel-status", action="store_true",
        help="P02: единый read-only status Plan/Run/owned resources для GUI/CLI",
    )
    parser.add_argument(
        "--runtime-migrate-state", action="store_true",
        help="P02: explicit receipted MigrationTxn legacy runtime session state",
    )
    parser.add_argument(
        "--privileged-executor-status", action="store_true",
        help="P02: проверить root-owned bounded executor и provenance hash; read-only",
    )
    parser.add_argument(
        "--privileged-executor-install-plan", action="store_true",
        help="P02: показать явную install-команду bounded executor; ничего не устанавливает",
    )
    parser.add_argument(
        "--gui-first-overview",
        action="store_true",
        help="показать GUI-first state machine summary: selected/prepared/running/firewall; без исполнения",
    )
    parser.add_argument(
        "--gui-first-developer",
        action="store_true",
        help="добавить developer details к --gui-first-overview",
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
        "--har-plan",
        action="store_true",
        help="показать privacy-aware план универсального анализа HAR; без чтения файла",
    )
    parser.add_argument(
        "--har-analyze",
        metavar="HAR_OR_ZIP",
        help="прочитать HAR любого ресурса и сохранить sanitized host/path/status/L7/error summary",
    )
    parser.add_argument(
        "--har-report",
        action="store_true",
        help="показать последний универсальный sanitized HAR summary",
    )
    parser.add_argument(
        "--har-workbench",
        metavar="HAR_OR_ZIP",
        help="универсальный HAR import, family/L7/error grouping, Blockcheck inputs и preset blueprint",
    )
    parser.add_argument(
        "--har-workbench-report",
        action="store_true",
        help="показать последний универсальный HAR workbench",
    )
    parser.add_argument(
        "--har-group-plan",
        metavar="GROUP_ID",
        help="показать Blockcheck plan для группы последнего универсального HAR workbench",
    )
    parser.add_argument(
        "--discord-har-plan",
        action="store_true",
        help="показать privacy-aware план анализа HAR Discord; без чтения файла",
    )
    parser.add_argument(
        "--discord-har-analyze",
        metavar="HAR_OR_ZIP",
        help="прочитать HAR/.zip локально и сохранить sanitized host/path/status summary без секретов",
    )
    parser.add_argument(
        "--discord-har-report",
        action="store_true",
        help="показать последний sanitized Discord HAR summary",
    )
    parser.add_argument(
        "--discord-har-workbench",
        metavar="HAR_OR_ZIP",
        help="sanitized HAR import, L7 grouping, Blockcheck group files и preset blueprint; без sudo/run",
    )
    parser.add_argument(
        "--discord-har-workbench-report",
        action="store_true",
        help="показать последний Discord HAR workbench",
    )
    parser.add_argument(
        "--discord-har-group-plan",
        metavar="GROUP_ID",
        help="показать Blockcheck plan для группы последнего HAR workbench; без запуска",
    )
    parser.add_argument(
        "--discord-voice-profiles",
        action="store_true",
        help="показать перенесённые Discord Voice Linux/nfqws2 профили и их источники",
    )
    parser.add_argument(
        "--discord-endpoint-seconds",
        type=int,
        default=DEFAULT_DISCOVERY_SECONDS,
        help="длительность --discord-endpoint-watch в секундах: 1..600",
    )
    parser.add_argument(
        "--discord-dns-edge-plan",
        action="store_true",
        help="показать read-only план проверки DNS edge для Discord; без запуска",
    )
    parser.add_argument(
        "--discord-dns-edge-check",
        action="store_true",
        help="read-only диагностика: сравнить DNS resolvers и TCP/443 доступность Discord edge IP",
    )
    parser.add_argument(
        "--discord-dns-edge-resolvers",
        default=",".join(DEFAULT_DNS_EDGE_RESOLVERS),
        help="resolver ids для --discord-dns-edge-check через запятую: system,cloudflare,google,quad9,adguard,opendns",
    )
    parser.add_argument(
        "--discord-dns-edge-hosts",
        default=None,
        help="host override для DNS edge check; по умолчанию Discord updater/app/gateway/CDN hosts",
    )
    parser.add_argument(
        "--discord-dns-edge-timeout",
        type=float,
        default=3.0,
        help="TCP connect timeout для каждого edge IP: 0.5..15 секунд",
    )

    parser.add_argument(
        "--external-reference-audit",
        action="store_true",
        help="показать read-only Stage 7o0 audit внешних рабочих zapret/Linux/Windows reference-решений; без запуска внешних скриптов",
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
        help="совместимость: upstream DNS precheck уже включён по умолчанию",
    )
    parser.add_argument(
        "--blockcheck-skip-dnscheck",
        action="store_true",
        help="явно пропустить upstream DNS precheck; mdig всё равно нужен для strategy tests",
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
        "--list-presets",
        action="store_true",
        help="показать каталог пресетов и число profile-блоков без исполнения",
    )
    parser.add_argument(
        "--show-preset",
        metavar="PRESET_ID",
        help="показать порядок profile-блоков одного пресета",
    )
    parser.add_argument(
        "--show-preset-profile",
        nargs=2,
        metavar=("PRESET_ID", "PROFILE_ID_OR_NUMBER"),
        help="показать filter/strategy/range/direction одного profile-блока",
    )
    parser.add_argument(
        "--select-preset",
        metavar="PRESET_ID",
        help="выбрать пресет для Default workspace; только сохраняет .zap2 selection",
    )
    parser.add_argument(
        "--list-profiles",
        action="store_true",
        help="legacy: показать workspace contexts без применения настроек",
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
        skip_dnscheck=bool(args.blockcheck_skip_dnscheck and not args.blockcheck_dnscheck),
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

    if args.security_blocklist_status:
        print(security_blocklist_status().to_text()); return 0
    if args.security_blocklist_enable or args.security_blocklist_enable_inbound:
        set_security_blocklist_enabled(None, True, inbound=bool(args.security_blocklist_enable_inbound), outbound=True)
        print(security_blocklist_status().to_text()); return 0
    if args.security_blocklist_disable:
        try:
            set_security_blocklist_enabled(None, False)
            print(remove_security_blocklist().to_text()); return 0
        except ValueError as exc:
            print(str(exc), file=sys.stderr); return 2
    if args.security_blocklist_update:
        try:
            print(update_security_blocklist().to_text()); return 0
        except (OSError, ValueError) as exc:
            print(str(exc), file=sys.stderr); return 2
    if args.security_blocklist_apply:
        try:
            print(apply_security_blocklist().to_text()); return 0
        except ValueError as exc:
            print(str(exc), file=sys.stderr); return 2
    if args.security_blocklist_refresh:
        try:
            print(refresh_security_blocklist().to_text()); return 0
        except (OSError, ValueError) as exc:
            print(str(exc), file=sys.stderr); return 2
    if args.security_blocklist_timer_plan:
        service_name,timer_name,service,timer=security_blocklist_timer_plan()
        print(f"===== {service_name} =====\n{service}\n===== {timer_name} =====\n{timer}"); return 0
    if args.security_blocklist_install_timer:
        try:
            print(install_security_blocklist_timer().to_text()); return 0
        except (OSError, ValueError) as exc:
            print(str(exc), file=sys.stderr); return 2
    if args.security_blocklist_remove_timer:
        try:
            print(remove_security_blocklist_timer().to_text()); return 0
        except (OSError, ValueError) as exc:
            print(str(exc), file=sys.stderr); return 2


    if args.launch_composer_status:
        try:
            print(launch_composer_status_to_text(components=args.launch_components, profile_id=args.profile, core_binary=args.tunnel_core_binary))
            return 0
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    if args.launch_composer_plan:
        try:
            print(launch_composer_plan_to_text(components=args.launch_components, profile_id=args.profile, core_binary=args.tunnel_core_binary, core_kind=args.tunnel_core_kind, socks_port=args.tunnel_socks_port))
            return 0
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    if args.launch_composer_start:
        try:
            print(launch_composer_start_to_text(components=args.launch_components, profile_id=args.profile, core_binary=args.tunnel_core_binary, core_kind=args.tunnel_core_kind, socks_port=args.tunnel_socks_port))
            return 0
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    if args.launch_composer_stop:
        try:
            print(launch_composer_stop_to_text(components=args.launch_components, profile_id=args.profile))
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

    if args.har_plan:
        print(har_plan_to_text())
        return 0

    if args.har_analyze:
        try:
            print(har_analyze_to_text(str(args.har_analyze)))
            return 0
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"HAR analyze failed: {exc}", file=sys.stderr)
            return 2

    if args.har_report:
        print(har_report_to_text())
        return 0

    if args.har_workbench:
        try:
            print(har_workbench_to_text(str(args.har_workbench)))
            return 0
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"HAR workbench failed: {exc}", file=sys.stderr)
            return 2

    if args.har_workbench_report:
        print(har_workbench_report_to_text())
        return 0

    if args.har_group_plan:
        try:
            print(har_group_plan_to_text(str(args.har_group_plan)))
            return 0
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"HAR group plan failed: {exc}", file=sys.stderr)
            return 2

    if args.discord_har_plan:
        print(discord_har_plan_to_text())
        return 0

    if args.discord_har_analyze:
        try:
            print(discord_har_analyze_to_text(str(args.discord_har_analyze)))
            return 0
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"Discord HAR analyze failed: {exc}", file=sys.stderr)
            return 2

    if args.discord_har_report:
        print(discord_har_report_to_text())
        return 0

    if args.discord_har_workbench:
        try:
            print(discord_har_workbench_to_text(str(args.discord_har_workbench)))
            return 0
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"Discord HAR workbench failed: {exc}", file=sys.stderr)
            return 2

    if args.discord_har_workbench_report:
        print(discord_har_workbench_report_to_text())
        return 0

    if args.discord_har_group_plan:
        try:
            print(discord_har_group_plan_to_text(str(args.discord_har_group_plan)))
            return 0
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"Discord HAR group plan failed: {exc}", file=sys.stderr)
            return 2

    if args.discord_voice_profiles:
        try:
            print(discord_voice_profiles_to_text())
            return 0
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"Discord Voice profile inventory failed: {exc}", file=sys.stderr)
            return 2

    if args.discord_dns_edge_plan:
        print(discord_dns_edge_plan_to_text(hosts=args.discord_dns_edge_hosts, resolvers=args.discord_dns_edge_resolvers, timeout_seconds=args.discord_dns_edge_timeout))
        return 0

    if args.discord_dns_edge_check:
        print(discord_dns_edge_check_to_text(hosts=args.discord_dns_edge_hosts, resolvers=args.discord_dns_edge_resolvers, timeout_seconds=args.discord_dns_edge_timeout))
        return 0

    if args.external_reference_audit:
        print(external_reference_audit_to_text())
        return 0

    if args.tunnel_connection_import_vless:
        try:
            print(tunnel_connection_import_vless_to_text(str(args.tunnel_connection_import_vless), profile_id=args.profile))
            return 0
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    if args.tunnel_connections:
        print(tunnel_connections_to_text(profile_id=args.profile))
        return 0

    if args.tunnel_select_connection:
        try:
            print(select_tunnel_connection(str(args.tunnel_select_connection), profile_id=args.profile))
            return 0
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    if args.tor_backend_plan:
        try:
            print(tor_backend_plan_to_text(profile_id=args.profile, backend=args.tor_backend, binary=args.tor_binary, socks_port=args.tor_socks_port))
            return 0
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    if args.tor_backend_start:
        try:
            print(tor_backend_start_to_text(profile_id=args.profile, backend=args.tor_backend, confirm_plan_id=args.confirm or ""))
            return 0
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    if args.tor_backend_status:
        print(tor_backend_status_to_text(profile_id=args.profile))
        return 0

    if args.tor_backend_stop:
        print(tor_backend_stop_to_text(profile_id=args.profile))
        return 0

    if args.discord_tunnel_plan:
        try:
            print(discord_tunnel_plan_to_text(profile_id=args.profile, core_binary=args.tunnel_core_binary, core_kind=args.tunnel_core_kind, socks_port=args.tunnel_socks_port))
            return 0
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    if args.discord_tunnel_core_preflight:
        try:
            print(discord_tunnel_core_preflight_to_text(profile_id=args.profile, core_binary=args.tunnel_core_binary, core_kind=args.tunnel_core_kind, socks_port=args.tunnel_socks_port))
            return 0
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    if args.discord_tunnel_start:
        try:
            print(discord_tunnel_start_to_text(profile_id=args.profile, confirm_plan_id=args.confirm or "", allow_parallel_with_zapret=bool(args.tunnel_allow_zapret_parallel)))
            return 0
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    if args.discord_tunnel_stop:
        try:
            print(discord_tunnel_stop_to_text(profile_id=args.profile))
            return 0
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    if args.discord_tunnel_status:
        print(discord_tunnel_status_to_text(profile_id=args.profile))
        return 0

    if args.discord_tunnel_probe:
        print(discord_tunnel_probe_to_text(profile_id=args.profile))
        return 0

    if args.discord_tunnel_https_probe:
        try:
            print(discord_tunnel_https_probe_to_text(profile_id=args.profile, target_host=str(args.tunnel_probe_host), target_path=str(args.tunnel_probe_path), timeout_seconds=float(args.tunnel_probe_timeout)))
            return 0
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    if args.discord_tunnel_route_diagnose:
        print(discord_tunnel_route_diagnose_to_text(profile_id=args.profile))
        return 0

    if args.discord_tunnel_evidence:
        print(discord_tunnel_evidence_to_text(profile_id=args.profile))
        return 0

    if args.discord_tunnel_guided_run:
        try:
            text = discord_tunnel_guided_run_to_text(
                profile_id=args.profile,
                core_binary=args.tunnel_core_binary,
                core_kind=args.tunnel_core_kind,
                socks_port=args.tunnel_socks_port,
                discord_binary=str(args.discord_binary),
                launch_mode=str(args.discord_launch_mode),
                observe_seconds=args.tunnel_observe_seconds,
                updater_result=str(args.discord_updater_result),
                interactive=not args.tunnel_guided_no_wait,
                emit=print,
            )
            print(text)
            return 0
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    if args.discord_tunnel_tun_plan:
        print(discord_tunnel_tun_plan_to_text(profile_id=args.profile))
        return 0

    if args.discord_proxy_route_plan:
        print(discord_proxy_route_plan_to_text(profile_id=args.profile))
        return 0

    if args.discord_launch_through_socks:
        try:
            print(discord_launch_through_socks_to_text(
                profile_id=args.profile,
                discord_binary=str(args.discord_binary),
                launch_mode=str(args.discord_launch_mode),
                upstream_preflight=bool(args.discord_launch_preflight),
                preflight_host=str(args.tunnel_probe_host),
                preflight_path=str(args.tunnel_probe_path),
                preflight_timeout=float(args.tunnel_probe_timeout),
                allow_failed_preflight=bool(args.discord_launch_allow_failed_preflight),
            ))
            return 0
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    if args.discord_stop_launched:
        try:
            print(discord_stop_launched_to_text(profile_id=args.profile))
            return 0
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    if args.strategy_parser_preflight:
        try:
            print(strategy_parser_preflight_to_text(profile_id=args.profile))
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
            print(execute_bounded_owner_rules(action="apply", profile_id=args.profile, confirm_plan_id=args.confirm or "").to_text())
            return 0
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    if args.runtime_revert:
        try:
            print(execute_bounded_owner_rules(action="revert", profile_id=args.profile, confirm_plan_id=args.confirm or "").to_text())
            return 0
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    if args.runtime_reconcile:
        try:
            print(reconcile_runtime_owner_rules(profile_id=args.profile).to_text())
            return 0
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    if args.runtime_session_start:
        try:
            print(execute_bounded_session_start(profile_id=args.profile).to_text())
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

    if args.runtime_nft_state:
        try:
            print(runtime_nft_state_to_text(profile_id=args.profile))
            return 0
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    if args.runtime_pretls_probe:
        try:
            print(runtime_pretls_probe_to_text(profile_id=args.profile))
            return 0
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2


    if args.runtime_discord_pretls_guided_probe:
        try:
            text = runtime_discord_pretls_guided_probe_to_text(
                profile_id=args.profile,
                wait_seconds=args.pretls_probe_wait_seconds,
                interactive=not args.pretls_probe_no_wait,
                emit=print,
            )
            print(text)
            return 0
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    if args.discord_observation_matrix_plan:
        try:
            print(discord_observation_matrix_plan_to_text(profile_id=args.profile))
            return 0
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    if args.discord_observation_matrix_report:
        try:
            print(discord_observation_matrix_report_to_text(profile_id=args.profile))
            return 0
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    if args.discord_observation_matrix_run_row:
        try:
            print(
                discord_observation_matrix_run_row_to_text(
                    row_id=str(args.discord_observation_matrix_run_row),
                    profile_id=args.profile,
                    wait_seconds=args.matrix_row_wait_seconds,
                    interactive=not args.matrix_row_no_wait,
                    auto=args.matrix_row_auto,
                    emit=print,
                )
            )
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
        print(
            "P02 service truth: plan-only. Privileged systemd install/remove is not part of the finite standard executor; "
            "use --service-plan for review. Execution is intentionally staged/unsupported in P02.",
            file=sys.stderr,
        )
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
            result = execute_bounded_default_workflow(action="start", profile_id=args.profile, confirm_plan_id=args.confirm or "")
            print(result.to_text())
            return 0 if result.state == "started" else 1
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    if args.privileged_executor_status:
        print(privileged_executor_status().to_text())
        return 0

    if args.privileged_executor_install_plan:
        print(privileged_executor_install_command())
        return 0

    if args.runtime_migrate_state:
        try:
            print(migrate_runtime_session_state(profile_id=args.profile).to_text())
            return 0
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    if args.runtime_kernel_status:
        try:
            print(runtime_kernel_status(profile_id=args.profile).to_text())
            return 0
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

    if args.gui_first_overview:
        try:
            print(gui_first_runtime_overview_to_text(profile_id=args.profile, developer=bool(args.gui_first_developer)))
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
            result = execute_bounded_default_workflow(action="stop", profile_id=args.profile, confirm_plan_id=args.confirm or "")
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

    if args.select_preset:
        try:
            print(select_preset(args.select_preset, workspace_id=args.profile).to_text())
            return 0
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

    if args.list_presets:
        print(preset_catalog_to_text())
        return 0

    if args.show_preset:
        try:
            print(preset_to_text(args.show_preset))
            return 0
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    if args.show_preset_profile:
        try:
            preset_id, profile_id = args.show_preset_profile
            print(preset_profile_to_text(preset_id, profile_id))
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
