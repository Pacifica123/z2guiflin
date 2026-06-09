"""Service target preset registry for Blockcheck-oriented discovery.

The registry is intentionally small and data-only at v0.4-alpha Stage 2. It
provides one source of truth for the target lists that Blockcheck lab should use
later from GUI/CLI preset selectors, while keeping runtime apply unchanged.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

SERVICE_TARGET_YOUTUBE_BASIC = "youtube-basic"
SERVICE_TARGET_DISCORD_DESKTOP = "discord-desktop"
SERVICE_TARGET_CUSTOM = "custom"
DEFAULT_SERVICE_TARGET_PRESET_ID = SERVICE_TARGET_YOUTUBE_BASIC

_SAFE_TARGET_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/?=&%+~#@-]{0,250}$")
_PRESET_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,60}[a-z0-9]$")


@dataclass(frozen=True)
class ServiceTargetPreset:
    """Named service target list used as an owner-visible Blockcheck seed."""

    preset_id: str
    title: str
    summary: str
    targets: tuple[str, ...]
    layers: dict[str, tuple[str, ...]] | None = None
    mode: str = "preset"
    non_voice: bool = True

    @property
    def is_custom(self) -> bool:
        return self.mode == SERVICE_TARGET_CUSTOM

    @property
    def target_string(self) -> str:
        return " ".join(self.targets)

    def validate(self) -> None:
        validate_preset_id(self.preset_id)
        if not self.title.strip():
            raise ValueError(f"service target preset {self.preset_id!r} must have a title")
        if self.mode not in {"preset", SERVICE_TARGET_CUSTOM}:
            raise ValueError(f"service target preset {self.preset_id!r} has unsupported mode: {self.mode!r}")
        if self.is_custom:
            if self.targets:
                raise ValueError("custom service target preset must not carry fixed targets")
            return
        validate_service_targets(self.targets)
        if self.layers is not None:
            layer_targets: list[str] = []
            for layer_name, targets in self.layers.items():
                if not layer_name.strip():
                    raise ValueError(f"service target preset {self.preset_id!r} has an empty layer name")
                validate_service_targets(tuple(targets))
                layer_targets.extend(targets)
            if tuple(layer_targets) != self.targets:
                raise ValueError(f"service target preset {self.preset_id!r} layers must match targets order exactly")


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


_SERVICE_TARGET_PRESETS = (
    ServiceTargetPreset(
        preset_id=SERVICE_TARGET_YOUTUBE_BASIC,
        title="YouTube basic",
        summary="Проверенный v0.3-stable baseline: базовые YouTube-домены для HTTPS/TLS/QUIC Blockcheck.",
        targets=("youtube.com", "www.youtube.com"),
    ),
    ServiceTargetPreset(
        preset_id=SERVICE_TARGET_DISCORD_DESKTOP,
        title="Discord desktop non-voice",
        summary=(
            "Первичный v0.4-alpha seed для desktop Discord без voice/UDP: login, gateway, "
            "updates и CDN/media targets."
        ),
        targets=(
            "discord.com",
            "gateway.discord.gg",
            "cdn.discordapp.com",
            "discordapp.net",
            "discord.media",
            "media.discordapp.net",
            "updates.discord.com",
            "stable.dl2.discordapp.net",
            "discord.gg",
        ),
        layers={
            "app-api-gateway": ("discord.com", "gateway.discord.gg"),
            "cdn-media": ("cdn.discordapp.com", "discordapp.net", "discord.media", "media.discordapp.net"),
            "updater": ("updates.discord.com", "stable.dl2.discordapp.net"),
            "invite": ("discord.gg",),
        },
        non_voice=True,
    ),
    ServiceTargetPreset(
        preset_id=SERVICE_TARGET_CUSTOM,
        title="Custom manual targets",
        summary="Безопасный ручной режим: владелец сам вводит домены/URI, а registry валидирует токены.",
        targets=(),
        mode=SERVICE_TARGET_CUSTOM,
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
