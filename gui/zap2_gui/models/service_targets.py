"""Service target preset registry for Blockcheck-oriented discovery.

The registry is intentionally service-oriented rather than Discord/YouTube-only.
Each preset now declares both its target list and its coverage policy so the
owner, GUI and Blockcheck adapter share the same answer to a basic question:
"is one working target enough, or do we need all/most targets to work?".
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

SERVICE_TARGET_YOUTUBE_BASIC = "youtube-basic"
SERVICE_TARGET_DISCORD_DESKTOP = "discord-desktop"
SERVICE_TARGET_CUSTOM = "custom"
DEFAULT_SERVICE_TARGET_PRESET_ID = SERVICE_TARGET_YOUTUBE_BASIC

SERVICE_COVERAGE_ANY_TARGET_AVAILABLE = "any-target-available"
SERVICE_COVERAGE_MAXIMIZE_TARGETS = "maximize-targets"
SERVICE_COVERAGE_ORDERED_TARGET_CHAIN = "ordered-target-chain"
SERVICE_COVERAGE_CUSTOM_MANUAL = "custom-manual"
SERVICE_COVERAGE_ORDER_NOT_IMPORTANT = "order-not-important"
SERVICE_COVERAGE_ORDER_IMPORTANT = "order-important"
SERVICE_COVERAGE_ORDER_OWNER_DEFINED = "owner-defined"
SUPPORTED_SERVICE_COVERAGE_POLICIES = (
    SERVICE_COVERAGE_ANY_TARGET_AVAILABLE,
    SERVICE_COVERAGE_MAXIMIZE_TARGETS,
    SERVICE_COVERAGE_ORDERED_TARGET_CHAIN,
    SERVICE_COVERAGE_CUSTOM_MANUAL,
)
SUPPORTED_SERVICE_COVERAGE_ORDER_MODES = (
    SERVICE_COVERAGE_ORDER_NOT_IMPORTANT,
    SERVICE_COVERAGE_ORDER_IMPORTANT,
    SERVICE_COVERAGE_ORDER_OWNER_DEFINED,
)

BLOCKCHECK_SCAN_STOP_AFTER_FIRST_AVAILABLE = "stop-after-first-available"
BLOCKCHECK_SCAN_ALL_TARGETS = "scan-all-targets"
BLOCKCHECK_SCAN_SKIP_DEAD_ONLY = "skip-dead-targets-only"

_SAFE_TARGET_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/?=&%+~#@-]{0,250}$")
_PRESET_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,60}[a-z0-9]$")


@dataclass(frozen=True)
class ServiceCoveragePhase:
    """One logical service phase: phases are AND, targets inside one phase are OR."""

    phase_id: str
    title: str
    targets: tuple[str, ...]
    required: bool = True
    summary: str = ""

    def validate(self, preset_id: str) -> None:
        validate_preset_id(self.phase_id)
        if not self.title.strip():
            raise ValueError(f"service target preset {preset_id!r} has a coverage phase without a title")
        validate_service_targets(self.targets)

    @property
    def target_string(self) -> str:
        return " ".join(self.targets)


@dataclass(frozen=True)
class ServiceCoveragePolicy:
    """Coverage semantics shared by user-facing presets and Blockcheck adapters."""

    mode: str
    order_mode: str
    summary: str
    required_targets: tuple[str, ...] = ()
    recommended_scan_mode: str = BLOCKCHECK_SCAN_STOP_AFTER_FIRST_AVAILABLE
    stop_rule: str = "owner-reviewed"

    @property
    def wants_ordered_chain(self) -> bool:
        return self.mode == SERVICE_COVERAGE_ORDERED_TARGET_CHAIN

    @property
    def accepts_any_available(self) -> bool:
        return self.mode == SERVICE_COVERAGE_ANY_TARGET_AVAILABLE

    @property
    def wants_best_coverage(self) -> bool:
        return self.mode in {SERVICE_COVERAGE_MAXIMIZE_TARGETS, SERVICE_COVERAGE_ORDERED_TARGET_CHAIN}

    def validate(self, preset_id: str, preset_targets: tuple[str, ...], *, is_custom: bool) -> None:
        if self.mode not in SUPPORTED_SERVICE_COVERAGE_POLICIES:
            raise ValueError(f"service target preset {preset_id!r} has unsupported coverage policy: {self.mode!r}")
        if self.order_mode not in SUPPORTED_SERVICE_COVERAGE_ORDER_MODES:
            raise ValueError(f"service target preset {preset_id!r} has unsupported coverage order mode: {self.order_mode!r}")
        if self.recommended_scan_mode not in {
            BLOCKCHECK_SCAN_STOP_AFTER_FIRST_AVAILABLE,
            BLOCKCHECK_SCAN_ALL_TARGETS,
            BLOCKCHECK_SCAN_SKIP_DEAD_ONLY,
        }:
            raise ValueError(f"service target preset {preset_id!r} has unsupported recommended scan mode: {self.recommended_scan_mode!r}")
        if not self.summary.strip():
            raise ValueError(f"service target preset {preset_id!r} coverage policy must have a summary")
        if is_custom:
            if self.mode != SERVICE_COVERAGE_CUSTOM_MANUAL:
                raise ValueError("custom service target preset must use custom-manual coverage policy")
            return
        validate_service_targets(self.required_targets or preset_targets)
        required = tuple(self.required_targets or preset_targets)
        preset_tokens = {service_target_host_token(item) for item in preset_targets}
        missing = [item for item in required if service_target_host_token(item) not in preset_tokens]
        if missing:
            raise ValueError(f"service target preset {preset_id!r} coverage policy references unknown targets: {missing!r}")
        if self.wants_ordered_chain and tuple(required) != tuple(preset_targets):
            raise ValueError(f"service target preset {preset_id!r} ordered policy must match preset target order")


@dataclass(frozen=True)
class ServiceTargetPreset:
    """Named service target list used as an owner-visible Blockcheck seed."""

    preset_id: str
    title: str
    summary: str
    targets: tuple[str, ...]
    layers: dict[str, tuple[str, ...]] | None = None
    phases: tuple[ServiceCoveragePhase, ...] = ()
    mode: str = "preset"
    non_voice: bool = True
    coverage_policy: ServiceCoveragePolicy | None = None

    @property
    def is_custom(self) -> bool:
        return self.mode == SERVICE_TARGET_CUSTOM

    @property
    def target_string(self) -> str:
        return " ".join(self.targets)

    @property
    def policy(self) -> ServiceCoveragePolicy:
        if self.coverage_policy is not None:
            return self.coverage_policy
        return ServiceCoveragePolicy(
            mode=SERVICE_COVERAGE_CUSTOM_MANUAL if self.is_custom else SERVICE_COVERAGE_ANY_TARGET_AVAILABLE,
            order_mode=SERVICE_COVERAGE_ORDER_OWNER_DEFINED if self.is_custom else SERVICE_COVERAGE_ORDER_NOT_IMPORTANT,
            summary="Manual targets are interpreted by the owner." if self.is_custom else "Any working target is enough for this simple preset.",
            required_targets=(),
            recommended_scan_mode=BLOCKCHECK_SCAN_STOP_AFTER_FIRST_AVAILABLE,
            stop_rule="owner-reviewed",
        )

    def ordered_targets_for_policy(self) -> tuple[str, ...]:
        if self.phases:
            return tuple(target for phase in self.phases for target in phase.targets)
        policy_targets = self.policy.required_targets
        return policy_targets if policy_targets else self.targets

    def phase_chain_for_policy(self) -> tuple[ServiceCoveragePhase, ...]:
        if self.phases:
            return self.phases
        if self.is_custom:
            return ()
        return tuple(
            ServiceCoveragePhase(phase_id=service_target_host_token(target).replace(".", "-"), title=str(target), targets=(target,))
            for target in self.ordered_targets_for_policy()
        )

    def validate(self) -> None:
        validate_preset_id(self.preset_id)
        if not self.title.strip():
            raise ValueError(f"service target preset {self.preset_id!r} must have a title")
        if self.mode not in {"preset", SERVICE_TARGET_CUSTOM}:
            raise ValueError(f"service target preset {self.preset_id!r} has unsupported mode: {self.mode!r}")
        if self.is_custom:
            if self.targets:
                raise ValueError("custom service target preset must not carry fixed targets")
            self.policy.validate(self.preset_id, self.targets, is_custom=True)
            return
        validate_service_targets(self.targets)
        self.policy.validate(self.preset_id, self.targets, is_custom=False)
        if self.phases:
            phase_targets: list[str] = []
            phase_ids: list[str] = []
            for phase in self.phases:
                phase.validate(self.preset_id)
                phase_ids.append(phase.phase_id)
                phase_targets.extend(phase.targets)
            if len(phase_ids) != len(set(phase_ids)):
                raise ValueError(f"service target preset {self.preset_id!r} has duplicate coverage phase ids")
            if tuple(service_target_host_token(item) for item in phase_targets) != tuple(service_target_host_token(item) for item in self.targets):
                raise ValueError(f"service target preset {self.preset_id!r} phase chain must cover targets in preset order")
        if self.layers is not None:
            layer_targets: list[str] = []
            for layer_name, targets in self.layers.items():
                if not layer_name.strip():
                    raise ValueError(f"service target preset {self.preset_id!r} has an empty layer name")
                validate_service_targets(tuple(targets))
                layer_targets.extend(targets)
            if set(service_target_host_token(item) for item in layer_targets) != set(service_target_host_token(item) for item in self.targets):
                raise ValueError(f"service target preset {self.preset_id!r} layers must cover the same targets")


def validate_preset_id(preset_id: str) -> None:
    if not _PRESET_ID_RE.fullmatch(preset_id):
        raise ValueError(f"invalid service target preset id: {preset_id!r}")


def normalize_service_targets(targets: str | tuple[str, ...] | list[str]) -> tuple[str, ...]:
    """Normalize and validate a manual target list.

    Targets are domain/URI-like tokens, separated by whitespace when passed as a
    string. Shell control characters and spaces inside one token are rejected.
    """

    if isinstance(targets, str):
        values = tuple(item.strip() for item in targets.split() if item.strip())
    else:
        values = tuple(str(item).strip() for item in targets if str(item).strip())
    validate_service_targets(values)
    return values


def service_target_host_token(target: str) -> str:
    """Return the hostlist token that should cover a service target.

    Stage 4 keeps presets domain-based, but this helper accepts simple URI-like
    targets too so future probes can be compared with hostlists without copying
    string parsing into tests or runtime adapters.
    """

    value = target.strip()
    if not value:
        return ""
    if "://" in value:
        parsed = urlparse(value)
        value = parsed.hostname or ""
    else:
        value = value.split("/", 1)[0]
        if value.startswith("[") and "]" in value:
            value = value[1:].split("]", 1)[0]
        else:
            value = value.split(":", 1)[0]
    value = value.strip().lower().rstrip(".")
    if value.startswith("*."):
        value = value[2:]
    return value


def hostlist_entries_from_text(text: str) -> tuple[str, ...]:
    """Parse owner-maintained hostlist text into comparable domain tokens."""

    entries: list[str] = []
    seen: set[str] = set()
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        token = service_target_host_token(line.split()[0])
        if not token or token in seen:
            continue
        seen.add(token)
        entries.append(token)
    return tuple(entries)


def service_targets_missing_from_hostlist(
    targets: tuple[str, ...] | list[str],
    hostlist_text: str,
) -> tuple[str, ...]:
    """Return preset targets whose host token is absent from hostlist text."""

    entries = set(hostlist_entries_from_text(hostlist_text))
    missing: list[str] = []
    for target in targets:
        token = service_target_host_token(str(target))
        if token and token not in entries:
            missing.append(str(target))
    return tuple(missing)


def service_target_preset_missing_from_hostlist(preset_id: str, hostlist_text: str) -> tuple[str, ...]:
    """Return missing hostlist entries for a non-custom service target preset."""

    preset = get_service_target_preset(preset_id)
    if preset.is_custom:
        raise ValueError("custom service target preset has no fixed hostlist coverage contract")
    return service_targets_missing_from_hostlist(preset.targets, hostlist_text)


def validate_service_targets(targets: tuple[str, ...] | list[str]) -> None:
    values = tuple(targets)
    if not values:
        raise ValueError("service target preset requires at least one target")
    seen: set[str] = set()
    for value in values:
        if not _SAFE_TARGET_RE.fullmatch(value):
            raise ValueError(
                "Недопустимый service target: "
                f"{value!r}. Разрешены домены/URI без пробелов и shell-символов."
            )
        lowered = value.lower()
        if lowered in seen:
            raise ValueError(f"duplicate service target in preset: {value!r}")
        seen.add(lowered)


_DISCORD_DESKTOP_PHASES = (
    ServiceCoveragePhase(
        phase_id="updater",
        title="Updater/bootstrap",
        targets=("stable.dl2.discordapp.net", "updates.discord.com"),
        summary="Any updater/download endpoint in this phase may satisfy the first Discord desktop boot phase.",
    ),
    ServiceCoveragePhase(
        phase_id="app-api",
        title="App/API",
        targets=("discord.com",),
        summary="Main app/API HTTPS target.",
    ),
    ServiceCoveragePhase(
        phase_id="gateway",
        title="Gateway",
        targets=("gateway.discord.gg",),
        summary="Persistent WebSocket gateway target.",
    ),
    ServiceCoveragePhase(
        phase_id="cdn-media",
        title="CDN/media",
        targets=("cdn.discordapp.com", "media.discordapp.net", "discord.media", "discordapp.net"),
        summary="Any media/CDN alternative proves this phase enough for the current non-voice loop.",
    ),
    ServiceCoveragePhase(
        phase_id="invite",
        title="Invite/secondary",
        targets=("discord.gg",),
        summary="Secondary invite target; useful but still tracked in the non-voice chain.",
    ),
)

_DISCORD_DESKTOP_ORDERED_TARGETS = tuple(target for phase in _DISCORD_DESKTOP_PHASES for target in phase.targets)

_SERVICE_TARGET_PRESETS = (
    ServiceTargetPreset(
        preset_id=SERVICE_TARGET_YOUTUBE_BASIC,
        title="YouTube basic",
        summary="Проверенный v0.3-stable baseline: базовые YouTube-домены для HTTPS/TLS/QUIC Blockcheck.",
        targets=("youtube.com", "www.youtube.com"),
        coverage_policy=ServiceCoveragePolicy(
            mode=SERVICE_COVERAGE_ANY_TARGET_AVAILABLE,
            order_mode=SERVICE_COVERAGE_ORDER_NOT_IMPORTANT,
            summary=(
                "Простой сервисный seed: достаточно найти любую рабочую стратегию хотя бы на одном "
                "из preset targets, затем владелец проверяет выбранный сервис вручную."
            ),
            required_targets=("youtube.com", "www.youtube.com"),
            recommended_scan_mode=BLOCKCHECK_SCAN_STOP_AFTER_FIRST_AVAILABLE,
            stop_rule="stop once first AVAILABLE target is observed",
        ),
    ),
    ServiceTargetPreset(
        preset_id=SERVICE_TARGET_DISCORD_DESKTOP,
        title="Discord desktop non-voice",
        summary=(
            "Первичный v0.4-alpha seed для desktop Discord без voice/UDP: updater, login, "
            "gateway и CDN/media targets."
        ),
        targets=_DISCORD_DESKTOP_ORDERED_TARGETS,
        layers={
            "updater": ("stable.dl2.discordapp.net", "updates.discord.com"),
            "app-api": ("discord.com",),
            "gateway": ("gateway.discord.gg",),
            "cdn-media": ("cdn.discordapp.com", "media.discordapp.net", "discord.media", "discordapp.net"),
            "invite": ("discord.gg",),
        },
        phases=_DISCORD_DESKTOP_PHASES,
        non_voice=True,
        coverage_policy=ServiceCoveragePolicy(
            mode=SERVICE_COVERAGE_ORDERED_TARGET_CHAIN,
            order_mode=SERVICE_COVERAGE_ORDER_IMPORTANT,
            summary=(
                "Desktop-style chain: фазы идут через AND, а targets внутри одной фазы считаются OR-альтернативами. "
                "Идеальная стратегия должна пройти updater → app/API → gateway → CDN/media; если это невозможно, UI показывает record-holder/best partial."
            ),
            required_targets=_DISCORD_DESKTOP_ORDERED_TARGETS,
            recommended_scan_mode=BLOCKCHECK_SCAN_ALL_TARGETS,
            stop_rule="test one strategy through the phase chain until full coverage is proven or owner stops and reviews the record-holder",
        ),
    ),
    ServiceTargetPreset(
        preset_id=SERVICE_TARGET_CUSTOM,
        title="Custom manual targets",
        summary="Безопасный ручной режим: владелец сам вводит домены/URI, а registry валидирует токены.",
        targets=(),
        mode=SERVICE_TARGET_CUSTOM,
        coverage_policy=ServiceCoveragePolicy(
            mode=SERVICE_COVERAGE_CUSTOM_MANUAL,
            order_mode=SERVICE_COVERAGE_ORDER_OWNER_DEFINED,
            summary="Ручной режим не навязывает семантику покрытия: владелец сам решает, достаточно ли одного target или всей цепочки.",
            required_targets=(),
            recommended_scan_mode=BLOCKCHECK_SCAN_STOP_AFTER_FIRST_AVAILABLE,
            stop_rule="owner-defined",
        ),
    ),
)

SERVICE_TARGET_PRESETS: dict[str, ServiceTargetPreset] = {item.preset_id: item for item in _SERVICE_TARGET_PRESETS}
for _preset in SERVICE_TARGET_PRESETS.values():
    _preset.validate()
if len(SERVICE_TARGET_PRESETS) != len(_SERVICE_TARGET_PRESETS):
    raise ValueError("duplicate service target preset ids")


YOUTUBE_BASIC_TARGETS = SERVICE_TARGET_PRESETS[SERVICE_TARGET_YOUTUBE_BASIC].targets
DISCORD_DESKTOP_TARGETS = SERVICE_TARGET_PRESETS[SERVICE_TARGET_DISCORD_DESKTOP].targets
DEFAULT_BLOCKCHECK_TARGETS = YOUTUBE_BASIC_TARGETS
DEFAULT_BLOCKCHECK_TARGET_STRING = " ".join(DEFAULT_BLOCKCHECK_TARGETS)


def list_service_target_presets() -> tuple[ServiceTargetPreset, ...]:
    """Return presets in stable owner-facing order."""

    return _SERVICE_TARGET_PRESETS


def get_service_target_preset(preset_id: str) -> ServiceTargetPreset:
    """Return one preset by id or raise a user-readable error."""

    try:
        return SERVICE_TARGET_PRESETS[preset_id]
    except KeyError as exc:
        choices = ", ".join(SERVICE_TARGET_PRESETS)
        raise ValueError(f"unknown service target preset: {preset_id!r}; available: {choices}") from exc


def service_target_string(preset_id: str) -> str:
    """Return a whitespace-separated target string for non-custom presets."""

    preset = get_service_target_preset(preset_id)
    if preset.is_custom:
        raise ValueError("custom service target preset does not have a fixed target string")
    return preset.target_string


def service_target_policy(preset_id: str) -> ServiceCoveragePolicy:
    """Return coverage policy for a service target preset."""

    return get_service_target_preset(preset_id).policy


def service_target_ordered_targets(preset_id: str) -> tuple[str, ...]:
    """Return the target order that Blockcheck should use for the preset policy."""

    preset = get_service_target_preset(preset_id)
    if preset.is_custom:
        raise ValueError("custom service target preset does not have a fixed target order")
    return preset.ordered_targets_for_policy()


def service_target_phase_chain(preset_id: str) -> tuple[ServiceCoveragePhase, ...]:
    """Return logical coverage phases: phases are AND, targets inside each phase are OR."""

    preset = get_service_target_preset(preset_id)
    if preset.is_custom:
        raise ValueError("custom service target preset does not have a fixed phase chain")
    return preset.phase_chain_for_policy()


def service_target_phase_for_target(preset_id: str, target: str) -> ServiceCoveragePhase | None:
    token = service_target_host_token(target)
    try:
        phases = service_target_phase_chain(preset_id)
    except ValueError:
        return None
    for phase in phases:
        if token in {service_target_host_token(item) for item in phase.targets}:
            return phase
    return None


def service_target_recommended_scan_mode(preset_id: str) -> str:
    """Return the scan mode that matches the preset coverage semantics."""

    return service_target_policy(preset_id).recommended_scan_mode


def service_target_coverage_policy_to_text(preset_id: str) -> str:
    """Render a read-only owner-facing description of preset coverage semantics."""

    preset = get_service_target_preset(preset_id)
    policy = preset.policy
    lines = [
        "Service target coverage policy",
        f"preset: {preset.preset_id} ({preset.title})",
        f"coverage mode: {policy.mode}",
        f"order mode: {policy.order_mode}",
        f"recommended scan mode: {policy.recommended_scan_mode}",
        f"stop rule: {policy.stop_rule}",
        f"summary: {policy.summary}",
    ]
    if preset.is_custom:
        lines.append("targets: owner-defined at runtime")
    else:
        phases = preset.phase_chain_for_policy()
        lines.append("phase order: phases use AND; targets inside a phase use OR")
        for index, phase in enumerate(phases, 1):
            marker = "required" if phase.required else "optional"
            lines.append(f"  {index}. {phase.phase_id} ({phase.title}; {marker}): {', '.join(phase.targets)}")
        lines.append("target order:")
        for index, target in enumerate(preset.ordered_targets_for_policy(), 1):
            phase = service_target_phase_for_target(preset.preset_id, target)
            phase_id = phase.phase_id if phase is not None else service_target_layer_for_target(preset.preset_id, target)
            lines.append(f"  {index}. {target} [{phase_id}]")
    lines.extend([
        "read-only: yes",
        "executes now: no",
        "mutates services/firewall now: no",
    ])
    return "\n".join(lines)


def infer_service_target_preset_id(targets: str | tuple[str, ...] | list[str]) -> str:
    """Infer a registry preset id from a target list, falling back to custom.

    Exact preset order is preferred. A single target that belongs to a preset is
    also enough for sequential Blockcheck logs: the GUI runs candidates one by
    one, but the owner-facing export should still stay attached to the service
    preset that launched the scan.
    """

    try:
        normalized = normalize_service_targets(targets)
    except ValueError:
        return SERVICE_TARGET_CUSTOM
    lowered = tuple(item.lower() for item in normalized)
    for preset in _SERVICE_TARGET_PRESETS:
        if preset.is_custom:
            continue
        preset_targets = tuple(item.lower() for item in preset.targets)
        if lowered == preset_targets:
            return preset.preset_id
    if len(lowered) == 1:
        target = lowered[0]
        matches = [
            preset.preset_id
            for preset in _SERVICE_TARGET_PRESETS
            if not preset.is_custom and target in tuple(item.lower() for item in preset.targets)
        ]
        if len(matches) == 1:
            return matches[0]
    return SERVICE_TARGET_CUSTOM


def service_target_export_slug(preset_id: str) -> str:
    """Return a stable slug suitable for generated strategy ids/files."""

    preset = get_service_target_preset(preset_id)
    return preset.preset_id if not preset.is_custom else SERVICE_TARGET_CUSTOM


def service_target_title(preset_id: str) -> str:
    """Return the owner-facing title for a preset id."""

    return get_service_target_preset(preset_id).title


def service_target_layer_for_target(preset_id: str, target: str) -> str:
    """Return the owner-facing service layer name for a target in a preset."""

    preset = get_service_target_preset(preset_id)
    token = service_target_host_token(target)
    if preset.layers:
        for layer_name, layer_targets in preset.layers.items():
            if token in {service_target_host_token(item) for item in layer_targets}:
                return layer_name
    return "custom" if preset.is_custom else "uncategorized"
