"""P04d executable ActionContract catalog.

P04d closes the action authority: every legacy top-level selector has a
canonical ActionContract. Curated P04c runtime/default contracts remain intact;
the remaining compatibility surface is generated once from the frozen parser
metadata and validated by the P04d acceptance checker.
"""
from __future__ import annotations

from .domain_semantics import ActionContract
from .action_bindings_generated import GENERATED_LEGACY_ACTION_SPECS


def _contract(
    action_id: str,
    label: str,
    effect: str,
    short_help: str,
    handler_id: str,
    *,
    aliases: tuple[str, ...] = (),
    keywords: tuple[str, ...] = (),
    concept_links: tuple[str, ...] = (),
    preconditions: tuple[str, ...] = (),
    privilege: str = "none",
    capability: str | None = None,
    location: str | None = None,
    focus_target: str | None = None,
    safe_invoke: bool = False,
    legacy_aliases: tuple[str, ...] = (),
) -> ActionContract:
    return ActionContract(
        action_id=action_id,
        label=label,
        effect=effect,
        short_help=short_help,
        handler_id=handler_id,
        aliases=aliases,
        keywords=keywords,
        concept_links=concept_links,
        preconditions=preconditions,
        privilege=privilege,
        capability=capability,
        location=location,
        focus_target=focus_target,
        safe_invoke=safe_invoke,
        legacy_aliases=legacy_aliases,
    )


P04C_ACTION_CONTRACTS: tuple[ActionContract, ...] = (
    _contract(
        "runtime.contracts.show",
        "Показать runtime contracts",
        "show",
        "Показать lifecycle contracts без исполнения.",
        "runtime.contracts.show",
        keywords=("runtime", "contracts", "lifecycle"),
        concept_links=("runtimeContext", "Plan"),
        safe_invoke=True,
        legacy_aliases=("--runtime-contracts",),
    ),
    _contract(
        "runtime.contracts.validate",
        "Проверить runtime contracts",
        "validate",
        "Проверить lifecycle contract catalog без исполнения.",
        "runtime.contracts.validate",
        keywords=("runtime", "contracts", "validate"),
        concept_links=("runtimeContext", "Plan"),
        safe_invoke=True,
        legacy_aliases=("--validate-runtime-contracts",),
    ),
    _contract(
        "runtime.plan.start",
        "План запуска runtime",
        "plan",
        "Материализовать immutable start Plan выбранного runtime context без исполнения.",
        "runtime.plan.start",
        keywords=("runtime", "plan", "start"),
        concept_links=("runtimeContext", "preset", "Plan"),
        safe_invoke=True,
        legacy_aliases=("--runtime-plan start",),
    ),
    _contract(
        "runtime.plan.stop",
        "План остановки runtime",
        "plan",
        "Материализовать immutable stop Plan выбранного runtime context без исполнения.",
        "runtime.plan.stop",
        keywords=("runtime", "plan", "stop"),
        concept_links=("runtimeContext", "preset", "Plan"),
        safe_invoke=True,
        legacy_aliases=("--runtime-plan stop",),
    ),
    _contract(
        "runtime.plan.status",
        "План статуса runtime",
        "plan",
        "Материализовать immutable status Plan выбранного runtime context без исполнения.",
        "runtime.plan.status",
        keywords=("runtime", "plan", "status"),
        concept_links=("runtimeContext", "preset", "Plan"),
        safe_invoke=True,
        legacy_aliases=("--runtime-plan status",),
    ),
    _contract(
        "runtime.logs.show",
        "Показать runtime log",
        "show",
        "Показать основной runtime log выбранного context.",
        "runtime.logs.show",
        keywords=("runtime", "log"),
        concept_links=("runtimeContext", "Evidence"),
        safe_invoke=True,
        legacy_aliases=("--runtime-log",),
    ),
    _contract(
        "runtime.logs.snapshot",
        "Показать runtime log snapshot",
        "show",
        "Показать read-only snapshot runtime logs выбранного context.",
        "runtime.logs.snapshot",
        keywords=("runtime", "logs", "snapshot"),
        concept_links=("runtimeContext", "Evidence"),
        safe_invoke=True,
        legacy_aliases=("--runtime-logs",),
    ),
    _contract(
        "runtime.owner-rules.plan.apply",
        "План применения owner-rules",
        "prepare",
        "Подготовить owner-confirmed nftables apply Plan без исполнения.",
        "runtime.owner-rules.plan.apply",
        keywords=("runtime", "nftables", "apply", "plan"),
        concept_links=("Plan", "runtimeResource"),
        safe_invoke=True,
        legacy_aliases=("--runtime-apply-plan",),
    ),
    _contract(
        "runtime.owner-rules.plan.revert",
        "План отката owner-rules",
        "prepare",
        "Подготовить owner-confirmed nftables revert Plan без исполнения.",
        "runtime.owner-rules.plan.revert",
        keywords=("runtime", "nftables", "revert", "plan"),
        concept_links=("Plan", "runtimeResource"),
        safe_invoke=True,
        legacy_aliases=("--runtime-revert-plan",),
    ),
    _contract(
        "runtime.owner-rules.apply",
        "Применить owner-rules",
        "apply",
        "Исполнить только заранее подтверждённый bounded owner-rules apply Plan.",
        "runtime.owner-rules.apply",
        keywords=("runtime", "nftables", "apply"),
        concept_links=("Plan", "runtimeResource"),
        preconditions=("confirmed Plan id supplied via --confirm",),
        privilege="bounded-root",
        legacy_aliases=("--runtime-apply",),
    ),
    _contract(
        "runtime.owner-rules.revert",
        "Откатить owner-rules",
        "revert",
        "Исполнить только заранее подтверждённый bounded owner-rules revert Plan.",
        "runtime.owner-rules.revert",
        keywords=("runtime", "nftables", "revert"),
        concept_links=("Plan", "runtimeResource"),
        preconditions=("confirmed Plan id supplied via --confirm",),
        privilege="bounded-root",
        legacy_aliases=("--runtime-revert",),
    ),
    _contract(
        "runtime.owner-rules.reconcile",
        "Сверить owner-rules",
        "reconcile",
        "Сверить saved owned state с observed nftables state без удаления unknown/conflict ресурсов.",
        "runtime.owner-rules.reconcile",
        keywords=("runtime", "nftables", "reconcile"),
        concept_links=("runtimeResource", "Evidence", "Verdict"),
        safe_invoke=True,
        legacy_aliases=("--runtime-reconcile",),
    ),
    _contract(
        "runtime.session.start",
        "Запустить runtime session",
        "start",
        "Запустить подтверждённую nfqws2 runtime session через bounded executor.",
        "runtime.session.start",
        keywords=("runtime", "session", "start", "nfqws2"),
        concept_links=("runtimeContext", "Plan", "backend/core"),
        privilege="bounded-root",
        legacy_aliases=("--runtime-session-start",),
    ),
    _contract(
        "runtime.session.status",
        "Статус runtime session",
        "show",
        "Показать read-only статус nfqws2 runtime session.",
        "runtime.session.status",
        keywords=("runtime", "session", "status"),
        concept_links=("runtimeContext", "Evidence"),
        safe_invoke=True,
        legacy_aliases=("--runtime-session-status",),
    ),
    _contract(
        "runtime.session.stop",
        "Остановить runtime session",
        "stop",
        "Остановить только session identity, записанную текущим runtime state.",
        "runtime.session.stop",
        keywords=("runtime", "session", "stop"),
        concept_links=("runtimeContext", "runtimeResource"),
        privilege="owner",
        legacy_aliases=("--runtime-session-stop",),
    ),
    _contract(
        "runtime.nft-state.show",
        "Показать runtime nft state",
        "show",
        "Показать read-only owned nftables/NFQUEUE state.",
        "runtime.nft-state.show",
        keywords=("runtime", "nftables", "nfqueue", "status"),
        concept_links=("runtimeResource", "Evidence"),
        safe_invoke=True,
        legacy_aliases=("--runtime-nft-state",),
    ),
    _contract(
        "runtime.kernel.status",
        "Показать runtime kernel status",
        "show",
        "Показать единый read-only Plan/Run/owned-resource status.",
        "runtime.kernel.status",
        keywords=("runtime", "kernel", "status"),
        concept_links=("Plan", "runtimeResource", "Evidence"),
        safe_invoke=True,
        legacy_aliases=("--runtime-kernel-status",),
    ),
    _contract(
        "default.build.dependencies.inspect",
        "Проверить зависимости сборки",
        "inspect",
        "Проверить зависимости default build target без установки пакетов и make.",
        "default.build.dependencies.inspect",
        keywords=("default", "build", "dependencies"),
        concept_links=("backend/core", "Capability"),
        safe_invoke=True,
        legacy_aliases=("--default-build-deps",),
    ),
    _contract(
        "default.build.plan",
        "План default build",
        "prepare",
        "Подготовить owner-confirmed local build Plan без запуска make.",
        "default.build.plan",
        keywords=("default", "build", "plan"),
        concept_links=("backend/core", "Plan"),
        safe_invoke=True,
        legacy_aliases=("--default-build-plan",),
    ),
    _contract(
        "default.build.apply",
        "Выполнить default build",
        "apply",
        "Исполнить подтверждённую локальную сборку default build target.",
        "default.build.apply",
        keywords=("default", "build"),
        concept_links=("backend/core", "Plan"),
        preconditions=("confirmed Plan id supplied via --confirm",),
        privilege="owner",
        legacy_aliases=("--default-build",),
    ),
    _contract(
        "default.workflow.plan.start",
        "План запуска Default workflow",
        "prepare",
        "Подготовить composite start Plan без исполнения.",
        "default.workflow.plan.start",
        keywords=("default", "workflow", "start", "plan"),
        concept_links=("runtimeContext", "preset", "Plan"),
        safe_invoke=True,
        legacy_aliases=("--default-start-plan",),
    ),
    _contract(
        "default.workflow.plan.stop",
        "План остановки Default workflow",
        "prepare",
        "Подготовить composite stop Plan без исполнения.",
        "default.workflow.plan.stop",
        keywords=("default", "workflow", "stop", "plan"),
        concept_links=("runtimeContext", "preset", "Plan"),
        safe_invoke=True,
        legacy_aliases=("--default-stop-plan",),
    ),
    _contract(
        "default.workflow.start",
        "Запустить Default workflow",
        "start",
        "Исполнить подтверждённый bounded start workflow: owner-rules + runtime session.",
        "default.workflow.start",
        keywords=("default", "workflow", "start"),
        concept_links=("runtimeContext", "preset", "Plan", "runtimeResource"),
        preconditions=("confirmed Plan id supplied via --confirm",),
        privilege="bounded-root",
        legacy_aliases=("--default-start",),
    ),
    _contract(
        "default.workflow.status",
        "Статус Default workflow",
        "show",
        "Показать read-only Default workflow/session status для GUI и CLI.",
        "default.workflow.status",
        keywords=("default", "workflow", "status"),
        concept_links=("runtimeContext", "Evidence", "Verdict"),
        safe_invoke=True,
        legacy_aliases=("--default-status",),
    ),
    _contract(
        "default.workflow.stop",
        "Остановить Default workflow",
        "stop",
        "Исполнить подтверждённый bounded stop workflow: session stop + owner-rules revert.",
        "default.workflow.stop",
        keywords=("default", "workflow", "stop"),
        concept_links=("runtimeContext", "preset", "Plan", "runtimeResource"),
        preconditions=("confirmed Plan id supplied via --confirm",),
        privilege="bounded-root",
        legacy_aliases=("--default-stop",),
    ),
    _contract(
        "privileged.executor.status",
        "Статус bounded executor",
        "show",
        "Проверить root-owned bounded executor и provenance hash без мутаций.",
        "privileged.executor.status",
        keywords=("privileged", "executor", "status", "provenance"),
        concept_links=("Capability", "Evidence"),
        safe_invoke=True,
        legacy_aliases=("--privileged-executor-status",),
    ),
    _contract(
        "privileged.executor.install-plan",
        "План установки bounded executor",
        "plan",
        "Показать явную install-команду bounded executor без установки.",
        "privileged.executor.install-plan",
        keywords=("privileged", "executor", "install", "plan"),
        concept_links=("Capability", "Plan"),
        safe_invoke=True,
        legacy_aliases=("--privileged-executor-install-plan",),
    ),
    _contract(
        "gui.overview.show",
        "Показать GUI-first overview",
        "show",
        "Показать GUI-first selected/prepared/running/firewall state machine summary.",
        "gui.overview.show",
        keywords=("gui", "overview", "status"),
        concept_links=("runtimeContext", "preset", "Evidence", "Verdict"),
        location="Overview",
        focus_target="runtimeStatusIndicator",
        safe_invoke=True,
        legacy_aliases=("--gui-first-overview",),
    ),
)


P04D_GENERATED_ACTION_CONTRACTS: tuple[ActionContract, ...] = tuple(
    _contract(
        action_id=str(spec["action_id"]),
        label=str(spec["label"]),
        effect=str(spec["effect"]),
        short_help=str(spec["short_help"]),
        handler_id=str(spec["handler_id"]),
        keywords=tuple(str(spec["selector"]).split("_")),
        privilege=str(spec["privilege"]),
        legacy_aliases=tuple(str(value) for value in spec["option_strings"]),
    )
    for spec in GENERATED_LEGACY_ACTION_SPECS
)

ACTION_CONTRACTS: tuple[ActionContract, ...] = P04C_ACTION_CONTRACTS + P04D_GENERATED_ACTION_CONTRACTS
ACTION_CONTRACT_BY_ID: dict[str, ActionContract] = {contract.action_id: contract for contract in ACTION_CONTRACTS}


def action_contract(action_id: str) -> ActionContract:
    try:
        return ACTION_CONTRACT_BY_ID[action_id]
    except KeyError as exc:
        raise ValueError(f"Unknown ActionContract: {action_id}") from exc


def action_contract_ids() -> tuple[str, ...]:
    return tuple(contract.action_id for contract in ACTION_CONTRACTS)


def action_projection_rows() -> tuple[dict[str, object], ...]:
    """Stable metadata projection shared by CLI/help/GUI tooling.

    This is deliberately generated from ActionContracts rather than maintained
    as a second registry. P05 may build richer search/help views on this shape.
    """

    return tuple(
        {
            "actionId": contract.action_id,
            "label": contract.label,
            "effect": contract.effect,
            "shortHelp": contract.short_help,
            "privilege": contract.privilege,
            "safeInvoke": contract.safe_invoke,
            "legacyAliases": list(contract.legacy_aliases),
            "conceptLinks": list(contract.concept_links),
        }
        for contract in ACTION_CONTRACTS
    )


def gui_runtime_action_contracts() -> tuple[ActionContract, ...]:
    """Small projection consumed by the current GUI runtime controls.

    The GUI does not own duplicate labels/help for these canonical actions; it
    reads them from the same ActionContracts that the dispatcher executes.
    """

    ids = (
        "default.workflow.start",
        "default.workflow.status",
        "default.workflow.stop",
    )
    return tuple(ACTION_CONTRACT_BY_ID[action_id] for action_id in ids)


def validation_errors() -> tuple[str, ...]:
    errors: list[str] = []
    seen_ids: set[str] = set()
    seen_legacy: set[str] = set()
    for contract in ACTION_CONTRACTS:
        for error in contract.validation_errors():
            errors.append(f"{contract.action_id}: {error}")
        if contract.action_id in seen_ids:
            errors.append(f"duplicate action_id: {contract.action_id}")
        seen_ids.add(contract.action_id)
        for alias in contract.legacy_aliases:
            if alias in seen_legacy:
                errors.append(f"duplicate legacy alias: {alias}")
            seen_legacy.add(alias)
    return tuple(errors)
