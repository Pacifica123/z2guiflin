#!/usr/bin/env python3
"""Read-only проверка структуры репозитория для v0.3-beta baseline."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_PATHS = [
    "README.md",
    "pyproject.toml",
    "core/README.md",
    "core/zapret2/UPSTREAM_IMPORT.json",
    "core/zapret2/UPSTREAM_IMPORT.md",
    "core/zapret2/CORE_INVENTORY.json",
    "core/zapret2/BUILD_MAP.json",
    "core/zapret2/docs/LICENSE.txt",
    "core/zapret2/Makefile",
    "core/zapret2/nfq2/Makefile",
    "core/zapret2/ip2net/Makefile",
    "core/zapret2/mdig/Makefile",
    "profiles/README.md",
    "profiles/default.json",
    "profiles/hostlists/default.hosts",
    "profiles/examples/lab-readonly.json",
    "strategies/README.md",
    "runtime/README.md",
    "strategies/catalog.json",
    "strategies/manual-local.json",
    "strategies/read-only-diagnostics.json",
    "runtime/schemas/runtime-plan.schema.json",
    "runtime/schemas/runtime-event.schema.json",
    "runtime/schemas/confirmation.schema.json",
    "runtime/examples/manual-local-start.contract.json",
    "runtime/examples/manual-local-start.event.json",
    "runtime/examples/manual-local-start.confirmation.json",
    "core/zapret2/nfq2/nfqws.c",
    "core/zapret2/lua/zapret-lib.lua",
    "gui/README.md",
    "gui/zap2_gui/__init__.py",
    "gui/zap2_gui/app.py",
    "gui/zap2_gui/core_inventory.py",
    "gui/zap2_gui/qt_compat.py",
    "gui/zap2_gui/qt_app.py",
    "gui/zap2_gui/adapters/gui_state.py",
    "gui/zap2_gui/adapters/local_build.py",
    "gui/zap2_gui/adapters/build_dependencies.py",
    "gui/zap2_gui/adapters/workspace_profiles.py",
    "gui/zap2_gui/adapters/runtime_contracts.py",
    "gui/zap2_gui/adapters/runtime_plan_generator.py",
    "gui/zap2_gui/adapters/runtime_state.py",
    "gui/zap2_gui/adapters/runtime_session.py",
    "gui/zap2_gui/adapters/runtime_apply.py",
    "gui/zap2_gui/adapters/runtime_service.py",
    "gui/zap2_gui/adapters/runtime_default.py",
    "gui/zap2_gui/adapters/runtime_default_build.py",
    "gui/zap2_gui/models/navigation.py",
    "gui/zap2_gui/models/strategy.py",
    "gui/zap2_gui/models/workspace_profile.py",
    "gui/zap2_gui/models/lifecycle.py",
    "gui/zap2_gui/models/runtime_plan.py",
    "gui/zap2_gui/models/runtime_events.py",
    "gui/zap2_gui/windows/main_window.py",
    "gui/zap2_gui/widgets/placeholders.py",
    "docs/DEVELOPMENT_STRATEGY.md",
    "docs/DOCUMENTATION_LANGUAGE.md",
    "docs/GUI_FRAMEWORK.md",
    "docs/GUI_SHELL.md",
    "docs/CORE_INVENTORY.md",
    "docs/CORE_BUILD_MAP.md",
    "docs/LOCAL_BUILD_ADAPTER.md",
    "docs/BUILD_DEPENDENCY_PREFLIGHT.md",
    "docs/BUILD_DEPENDENCY_PREFLIGHT.md",
    "docs/WORKSPACE_PROFILES.md",
    "docs/STRATEGIES.md",
    "docs/RUNTIME_LIFECYCLE.md",
    "docs/RUNTIME_PLANS.md",
    "docs/DEFAULT_RUNTIME_PLAN_GENERATOR.md",
    "docs/RUNTIME_STATE_AND_CONFIRMATION.md",
    "docs/RUNTIME_SESSION_RUNNER.md",
    "docs/RUNTIME_APPLY_REVERT.md",
    "docs/RUNTIME_SERVICE_PLANS.md",
    "docs/DEFAULT_WORKFLOW.md",
    "docs/DEFAULT_BUILD_WORKFLOW.md",
    "docs/PROJECT_STRUCTURE.md",
    "docs/VERSIONING.md",
    "docs/SAFETY_AND_PRIVILEGE_BOUNDARY.md",
    "docs/SOURCE_ALIGNMENT.md",
    "docs/reference/windows_gui_feature_digest.md",
    "docs/reference/legacy_project_digest.md",
    "strategies/imported/windows-default-v1-game-filter.txt",
    "strategies/imported/windows-default-v1-game-filter.json",
    "gui/zap2_gui/adapters/gui_runtime_controls.py",
    "gui/zap2_gui/widgets/runtime_controls.py",
    "docs/DEFAULT_STRATEGY_IMPORT.md",
    "docs/GUI_RUNTIME_CONTROLS.md",
    "tools/check_default_strategy_import.py",
    "tests/test_default_strategy_import_and_gui_controls.py",
    "tools/check_project_tree.py",
    "tools/inventory_core.py",
    "tools/check_local_build_adapter.py",
    "tools/check_workspace_profiles.py",
    "tools/check_runtime_lifecycle.py",
    "tools/check_runtime_plan_generator.py",
    "tools/check_runtime_state.py",
    "tools/check_runtime_session.py",
    "tools/check_runtime_apply.py",
    "tools/check_runtime_service.py",
    "tools/check_runtime_default.py",
    "tools/check_default_build_workflow.py",
    "tools/check_build_dependency_preflight.py",
    "tests/test_core_inventory_and_build_map.py",
    "tests/test_local_build_adapter.py",
    "tests/test_workspace_profiles_and_strategies.py",
    "tests/test_runtime_lifecycle_contracts.py",
    "tests/test_runtime_plan_generator.py",
    "tests/test_runtime_state_and_confirmation.py",
    "tests/test_runtime_session_runner.py",
    "tests/test_runtime_apply_revert.py",
    "tests/test_runtime_service_plans.py",
    "tests/test_default_workflow.py",
    "tests/test_default_build_workflow.py",
    "tests/test_build_dependency_preflight.py",
]

PROJECT_DOCUMENTATION_PATHS = [
    "README.md",
    "core/README.md",
    "core/zapret2/UPSTREAM_IMPORT.md",
    "gui/README.md",
    "profiles/README.md",
    "strategies/README.md",
    "runtime/README.md",
    "docs/DEVELOPMENT_STRATEGY.md",
    "docs/DOCUMENTATION_LANGUAGE.md",
    "docs/GUI_FRAMEWORK.md",
    "docs/GUI_SHELL.md",
    "docs/CORE_INVENTORY.md",
    "docs/CORE_BUILD_MAP.md",
    "docs/LOCAL_BUILD_ADAPTER.md",
    "docs/BUILD_DEPENDENCY_PREFLIGHT.md",
    "docs/BUILD_DEPENDENCY_PREFLIGHT.md",
    "docs/WORKSPACE_PROFILES.md",
    "docs/STRATEGIES.md",
    "docs/RUNTIME_LIFECYCLE.md",
    "docs/RUNTIME_PLANS.md",
    "docs/DEFAULT_RUNTIME_PLAN_GENERATOR.md",
    "docs/RUNTIME_STATE_AND_CONFIRMATION.md",
    "docs/RUNTIME_SESSION_RUNNER.md",
    "docs/RUNTIME_APPLY_REVERT.md",
    "docs/RUNTIME_SERVICE_PLANS.md",
    "docs/DEFAULT_WORKFLOW.md",
    "docs/DEFAULT_BUILD_WORKFLOW.md",
    "docs/PROJECT_STRUCTURE.md",
    "docs/SAFETY_AND_PRIVILEGE_BOUNDARY.md",
    "docs/SOURCE_ALIGNMENT.md",
    "docs/VERSIONING.md",
    "docs/reference/legacy_project_digest.md",
    "docs/reference/windows_gui_feature_digest.md",
]

FORBIDDEN_IMPORTED_SUFFIXES = (".o", ".a", ".exe", ".dll")
CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")


def _contains_russian_text(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    return len(CYRILLIC_RE.findall(text)) >= 80


def _run_inventory_check() -> bool:
    result = subprocess.run(
        [sys.executable, "tools/inventory_core.py", "--check"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    print(result.stdout.strip())
    return result.returncode == 0


def main() -> int:
    missing = [path for path in REQUIRED_PATHS if not (ROOT / path).exists()]
    if missing:
        print("Отсутствуют обязательные пути:")
        for path in missing:
            print(f" - {path}")
        return 1

    manifest_path = ROOT / "core/zapret2/UPSTREAM_IMPORT.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("upstreamName") != "bol-van/zapret2":
        print("Неожиданное upstreamName в манифесте импорта ядра")
        return 1
    if int(manifest.get("importedFileCount", 0)) <= 0:
        print("В манифесте импорта ядра нет импортированных файлов")
        return 1

    bad = [
        str(path.relative_to(ROOT)).replace("\\", "/")
        for path in (ROOT / "core/zapret2").rglob("*")
        if path.is_file() and path.name.lower().endswith(FORBIDDEN_IMPORTED_SUFFIXES)
    ]
    if bad:
        print("Неожиданные compiled/binary artifacts в импорте:")
        for path in bad:
            print(f" - {path}")
        return 1

    gui_framework_doc = (ROOT / "docs/GUI_FRAMEWORK.md").read_text(encoding="utf-8")
    strategy_doc = (ROOT / "docs/DEVELOPMENT_STRATEGY.md").read_text(encoding="utf-8")
    if "PyQt" not in gui_framework_doc or "PyQt" not in strategy_doc:
        print("Решение по PyQt GUI framework отсутствует в документации")
        return 1

    shell_doc = (ROOT / "docs/GUI_SHELL.md").read_text(encoding="utf-8")
    for section in ("Обзор", "Ядро", "Стратегии", "Диагностика", "Настройки", "Логи"):
        if section not in shell_doc:
            print(f"В документации GUI shell отсутствует раздел: {section}")
            return 1

    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    if "PyQt6" not in pyproject or "zap2-gui" not in pyproject:
        print("PyQt6 optional dependency или entry point zap2-gui не зафиксированы")
        return 1

    local_build_doc = (ROOT / "docs/LOCAL_BUILD_ADAPTER.md").read_text(encoding="utf-8")
    app_py = (ROOT / "gui/zap2_gui/app.py").read_text(encoding="utf-8")
    local_build_py = (ROOT / "gui/zap2_gui/adapters/local_build.py").read_text(encoding="utf-8")
    if "local build adapter" not in local_build_doc or "--build-plan" not in app_py:
        print("Local build adapter или CLI build-plan не зафиксированы")
        return 1
    if "automatic_checks_may_execute=False" not in local_build_py or "may_require_sudo=False" not in local_build_py:
        print("Local build adapter должен оставаться plan-only и без sudo")
        return 1

    workspace_doc = (ROOT / "docs/WORKSPACE_PROFILES.md").read_text(encoding="utf-8")
    strategies_doc = (ROOT / "docs/STRATEGIES.md").read_text(encoding="utf-8")
    workspace_adapter = (ROOT / "gui/zap2_gui/adapters/workspace_profiles.py").read_text(encoding="utf-8")
    if "workspace-проф" not in workspace_doc or "plan-only" not in strategies_doc:
        print("Документация workspace-профилей/стратегий не зафиксирована")
        return 1
    if "validate_workspace_catalog" not in workspace_adapter or "automatic_checks_may_execute_strategies" not in workspace_adapter:
        print("Workspace profiles adapter должен валидировать стратегии и read-only boundary")
        return 1

    runtime_doc = (ROOT / "docs/RUNTIME_LIFECYCLE.md").read_text(encoding="utf-8")
    runtime_plans_doc = (ROOT / "docs/RUNTIME_PLANS.md").read_text(encoding="utf-8")
    runtime_adapter = (ROOT / "gui/zap2_gui/adapters/runtime_contracts.py").read_text(encoding="utf-8")
    runtime_plan_schema = json.loads((ROOT / "runtime/schemas/runtime-plan.schema.json").read_text(encoding="utf-8"))
    runtime_contract = json.loads((ROOT / "runtime/examples/manual-local-start.contract.json").read_text(encoding="utf-8"))
    if "run plan" not in runtime_doc or "rollback" not in runtime_plans_doc:
        print("Документация runtime lifecycle contracts не зафиксирована")
        return 1
    if "validate_runtime_contract_catalog" not in runtime_adapter:
        print("Runtime contracts adapter должен валидировать контракты")
        return 1
    if "sections" not in runtime_plan_schema.get("required", []):
        print("runtime-plan schema должна требовать sections")
        return 1
    if runtime_contract["lifecycle"].get("automaticChecksMayExecute") is not False:
        print("Runtime contracts не должны исполняться автоматическими проверками")
        return 1
    if runtime_contract["lifecycle"].get("bootstrapMixedIn") is not False:
        print("Runtime contracts не должны смешиваться с bootstrap")
        return 1
    if {section["kind"] for section in runtime_contract["sections"]} != {"run", "apply", "session", "service"}:
        print("Runtime contract должен покрывать run/apply/session/service")
        return 1

    default_build_doc = (ROOT / "docs/DEFAULT_BUILD_WORKFLOW.md").read_text(encoding="utf-8")
    default_build_adapter = (ROOT / "gui/zap2_gui/adapters/runtime_default_build.py").read_text(encoding="utf-8")
    if "--default-build-plan" not in app_py or "--default-build" not in app_py:
        print("Default build workflow CLI-команды отсутствуют")
        return 1
    if "Default build workflow" not in default_build_doc or "без `sudo`" not in default_build_doc:
        print("Документация default build workflow не зафиксирована")
        return 1
    for required in ("DEFAULT_BUILD_MARKER", "prepare_default_build_plan", "execute_default_build", "rejectsRootExecutionByDefault"):
        if required not in default_build_adapter:
            print(f"Default build adapter не содержит обязательный элемент: {required}")
            return 1
    if "install_easy" in default_build_adapter or "systemctl" in default_build_adapter:
        print("Default build adapter не должен вызывать upstream installer scripts или service manager")
        return 1

    build_deps_doc = (ROOT / "docs/BUILD_DEPENDENCY_PREFLIGHT.md").read_text(encoding="utf-8")
    build_deps_adapter = (ROOT / "gui/zap2_gui/adapters/build_dependencies.py").read_text(encoding="utf-8")
    if "--default-build-deps" not in app_py or "Build dependency preflight" not in build_deps_doc:
        print("Build dependency preflight CLI/documentation отсутствуют")
        return 1
    for required in ("run_build_dependency_preflight", "BUILD_DEPENDENCY_MARKER", "libnetfilter_queue", "executes_install_now"):
        if required not in build_deps_adapter:
            print(f"Build dependency preflight adapter не содержит обязательный элемент: {required}")
            return 1
    forbidden_build_deps_fragments = ("subprocess", "os.system", "Popen", "check_call", "check_output", "install_prereq", "install_easy")
    for fragment in forbidden_build_deps_fragments:
        if fragment in build_deps_adapter:
            print(f"Build dependency preflight adapter не должен устанавливать пакеты или запускать shell: {fragment}")
            return 1

    default_workflow_doc = (ROOT / "docs/DEFAULT_WORKFLOW.md").read_text(encoding="utf-8")
    default_workflow_adapter = (ROOT / "gui/zap2_gui/adapters/runtime_default.py").read_text(encoding="utf-8")
    if "--default-start-plan" not in app_py or "--default-stop" not in app_py:
        print("Default workflow CLI-команды отсутствуют")
        return 1
    if "default-start" not in default_workflow_doc or "default-stop" not in default_workflow_doc:
        print("Документация default workflow не описывает запуск и отключение")
        return 1
    for required in ("DEFAULT_WORKFLOW_MARKER", "prepare_default_workflow_plan", "execute_default_workflow", "containsUpstreamInstallerScript"):
        if required not in default_workflow_adapter:
            print(f"Default workflow adapter не содержит обязательный элемент: {required}")
            return 1
    if "install_easy" in default_workflow_adapter or "systemctl" in default_workflow_adapter:
        print("Default workflow adapter не должен вызывать upstream installer scripts или service manager")
        return 1

    profiles_data = json.loads((ROOT / "profiles/default.json").read_text(encoding="utf-8"))
    strategies_catalog = json.loads((ROOT / "strategies/catalog.json").read_text(encoding="utf-8"))
    if profiles_data.get("strategyId") != "manual-local" or profiles_data.get("buildTarget") != "nfqws2":
        print("Default profile должен ссылаться на manual-local и nfqws2")
        return 1
    if strategies_catalog["safety"].get("automaticChecksMayExecuteStrategies") is not False:
        print("Strategy catalog должен запрещать исполнение стратегий в проверках")
        return 1

    runtime_generator_doc = (ROOT / "docs/DEFAULT_RUNTIME_PLAN_GENERATOR.md").read_text(encoding="utf-8")
    runtime_generator = (ROOT / "gui/zap2_gui/adapters/runtime_plan_generator.py").read_text(encoding="utf-8")
    if "Stage 9" not in runtime_generator_doc or "--runtime-plan" not in app_py:
        print("Runtime plan generator Stage 9 не зафиксирован в документации или CLI")
        return 1
    if "create_runtime_plan" not in runtime_generator or "SUPPORTED_RUNTIME_PLAN_ACTIONS" not in runtime_generator:
        print("Runtime plan generator должен иметь create_runtime_plan и явный список действий")
        return 1
    if "subprocess" in runtime_generator or "os.system" in runtime_generator:
        print("Runtime plan generator не должен исполнять shell/process commands")
        return 1

    runtime_state_doc = (ROOT / "docs/RUNTIME_STATE_AND_CONFIRMATION.md").read_text(encoding="utf-8")
    runtime_state_adapter = (ROOT / "gui/zap2_gui/adapters/runtime_state.py").read_text(encoding="utf-8")
    if "confirmation gate" not in runtime_state_doc or ".zap2/runtime" not in runtime_state_doc:
        print("Runtime state/confirmation gate Stage 10 не зафиксирован в документации")
        return 1
    required_runtime_state_symbols = (
        "prepare_runtime_plan",
        "confirm_runtime_plan",
        "runtime_log_to_text",
        "plan_payload_hash",
        "ensure_runtime_store",
    )
    for symbol in required_runtime_state_symbols:
        if symbol not in runtime_state_adapter:
            print(f"Runtime state adapter не содержит {symbol}")
            return 1
    forbidden_runtime_state_fragments = ("subprocess", "os.system", "systemctl", "iptables", "nft ", "curl", "wget")
    for fragment in forbidden_runtime_state_fragments:
        if fragment in runtime_state_adapter:
            print(f"Runtime state adapter не должен содержать execution/system fragment: {fragment}")
            return 1
    if "--runtime-prepare" not in app_py or "--runtime-confirm" not in app_py or "--runtime-log" not in app_py:
        print("CLI Stage 10 должен иметь runtime prepare/confirm/log commands")
        return 1

    runtime_session_doc = (ROOT / "docs/RUNTIME_SESSION_RUNNER.md").read_text(encoding="utf-8")
    runtime_session_adapter = (ROOT / "gui/zap2_gui/adapters/runtime_session.py").read_text(encoding="utf-8")
    if "session runner" not in runtime_session_doc or "nfqws2" not in runtime_session_doc:
        print("Runtime session runner Stage 11 не зафиксирован в документации")
        return 1
    required_runtime_session_symbols = (
        "start_runtime_session",
        "stop_runtime_session",
        "runtime_session_status",
        "build_runtime_session_config",
        "SESSION_MARKER",
    )
    for symbol in required_runtime_session_symbols:
        if symbol not in runtime_session_adapter:
            print(f"Runtime session adapter не содержит {symbol}")
            return 1
    forbidden_runtime_session_fragments = ("systemctl", "iptables", "nft ", "install_easy", "curl", "wget")
    for fragment in forbidden_runtime_session_fragments:
        if fragment in runtime_session_adapter:
            print(f"Runtime session adapter не должен содержать service/firewall/bootstrap fragment: {fragment}")
            return 1
    if "--runtime-session-start" not in app_py or "--runtime-session-stop" not in app_py or "--runtime-session-status" not in app_py:
        print("CLI Stage 11 должен иметь runtime session start/status/stop commands")
        return 1


    runtime_apply_doc = (ROOT / "docs/RUNTIME_APPLY_REVERT.md").read_text(encoding="utf-8")
    runtime_apply_adapter = (ROOT / "gui/zap2_gui/adapters/runtime_apply.py").read_text(encoding="utf-8")
    if "owner-confirmed" not in runtime_apply_doc or "nftables" not in runtime_apply_doc:
        print("Runtime apply/revert Stage 12 не зафиксирован в документации")
        return 1
    required_runtime_apply_symbols = (
        "create_runtime_apply_plan",
        "prepare_runtime_owner_rules_plan",
        "execute_runtime_owner_rules",
        "RuntimeApplyPlan",
        "APPLY_MARKER",
    )
    for symbol in required_runtime_apply_symbols:
        if symbol not in runtime_apply_adapter:
            print(f"Runtime apply adapter не содержит {symbol}")
            return 1
    if "install_easy" in runtime_apply_adapter or "curl" in runtime_apply_adapter or "wget" in runtime_apply_adapter:
        print("Runtime apply adapter не должен содержать remote/bootstrap installer fragments")
        return 1
    if "systemctl" in runtime_apply_adapter:
        print("Runtime apply adapter Stage 12 не должен управлять service mode")
        return 1
    if "nft" not in runtime_apply_adapter or "DEFAULT_NFT_TABLE_PREFIX" not in runtime_apply_adapter or "queue num" not in runtime_apply_adapter:
        print("Runtime apply adapter должен явно описывать nftables apply/revert")
        return 1
    if "--runtime-apply-plan" not in app_py or "--runtime-revert-plan" not in app_py or "--runtime-apply" not in app_py or "--runtime-revert" not in app_py:
        print("CLI Stage 12 должен иметь runtime apply/revert plan и execution commands")
        return 1


    runtime_service_doc = (ROOT / "docs/RUNTIME_SERVICE_PLANS.md").read_text(encoding="utf-8")
    runtime_service_adapter = (ROOT / "gui/zap2_gui/adapters/runtime_service.py").read_text(encoding="utf-8")
    if "service mode" not in runtime_service_doc or "Stage 13" not in runtime_service_doc:
        print("Runtime service plans Stage 13 не зафиксированы в документации")
        return 1
    required_runtime_service_symbols = (
        "create_service_plan",
        "prepare_service_plan",
        "execute_service_plan",
        "ServicePlan",
        "SERVICE_MARKER",
        "SUPPORTED_SERVICE_PLAN_ACTIONS",
    )
    for symbol in required_runtime_service_symbols:
        if symbol not in runtime_service_adapter:
            print(f"Runtime service adapter не содержит {symbol}")
            return 1
    if "install_easy" in runtime_service_adapter or "curl" in runtime_service_adapter or "wget" in runtime_service_adapter:
        print("Runtime service adapter не должен содержать remote/bootstrap installer fragments")
        return 1
    if "nft add" in runtime_service_adapter or "iptables" in runtime_service_adapter:
        print("Runtime service adapter не должен управлять firewall")
        return 1
    if "DEFAULT_SERVICE_DIR" not in runtime_service_adapter or "systemctl" not in runtime_service_adapter:
        print("Runtime service adapter должен явно описывать systemd service plans")
        return 1
    if "--service-plan" not in app_py or "--service-apply" not in app_py:
        print("CLI Stage 13 должен иметь service-plan и service-apply commands")
        return 1

    language_doc = (ROOT / "docs/DOCUMENTATION_LANGUAGE.md").read_text(encoding="utf-8")
    if "русском" not in language_doc or "проектная документация" not in language_doc:
        print("Правило русского языка документации не зафиксировано")
        return 1

    not_localized = [
        path
        for path in PROJECT_DOCUMENTATION_PATHS
        if not _contains_russian_text(ROOT / path)
    ]
    if not_localized:
        print("Активная проектная документация должна быть на русском языке:")
        for path in not_localized:
            print(f" - {path}")
        return 1

    inventory = json.loads((ROOT / "core/zapret2/CORE_INVENTORY.json").read_text(encoding="utf-8"))
    build_map = json.loads((ROOT / "core/zapret2/BUILD_MAP.json").read_text(encoding="utf-8"))
    if inventory["counts"]["vendorFileCount"] != int(manifest["importedFileCount"]):
        print("Инвентаризация ядра не совпадает с манифестом импорта")
        return 1
    unit_names = {unit["name"] for unit in build_map["units"]}
    if unit_names != {"nfqws2", "ip2net", "mdig"}:
        print("Build map должен описывать nfqws2, ip2net и mdig")
        return 1
    if build_map["safetyPolicy"].get("automaticChecksMayRunMake") is not False:
        print("Build map должен запрещать запуск make в автоматических проверках")
        return 1
    if not _run_inventory_check():
        return 1

    print("Дерево v0.3-beta OK; PyQt shell, русская документация, inventory, build map, local build adapter, build dependency preflight, default build workflow, workspace strategies и runtime lifecycle contracts, runtime plan generator и runtime state gate, session runner, owner-confirmed apply/revert, service plans и default workflow зафиксированы")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
