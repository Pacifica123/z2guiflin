"""Каталог пресетов Zapret2 поверх совместимых strategy metadata."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .workspace_profiles import (
    StrategySelectionResult,
    load_workspace_catalog,
    select_workspace_strategy,
)
from ..models.preset import TrafficProfile, ZapretPreset, parse_preset_args, validate_preset
from ..models.strategy import WorkspaceStrategy
from ..project_paths import discover_layout


@dataclass(frozen=True)
class PresetCatalogEntry:
    preset: ZapretPreset
    metadata: WorkspaceStrategy


@dataclass(frozen=True)
class PresetCatalog:
    entries: tuple[PresetCatalogEntry, ...]
    default_preset_id: str
    selected_preset_id: str

    def by_id(self) -> dict[str, PresetCatalogEntry]:
        return {entry.preset.preset_id: entry for entry in self.entries}

    @property
    def profile_count(self) -> int:
        return sum(len(entry.preset.profiles) for entry in self.entries)


def load_preset_catalog(root: Path | None = None) -> PresetCatalog:
    layout = discover_layout(root)
    workspace = load_workspace_catalog(layout.root)
    entries = tuple(
        PresetCatalogEntry(
            preset=parse_preset_args(
                strategy.runtime_args,
                preset_id=strategy.strategy_id,
                title=strategy.title,
                source_path=strategy.preset_path or "",
            ),
            metadata=strategy,
        )
        for strategy in workspace.strategies
    )
    selected = workspace.active_selection.strategy_id if workspace.active_selection else workspace.default_strategy_id
    return PresetCatalog(
        entries=entries,
        default_preset_id=workspace.default_strategy_id,
        selected_preset_id=selected,
    )


def load_preset(preset_id: str, root: Path | None = None) -> PresetCatalogEntry:
    catalog = load_preset_catalog(root)
    entries = catalog.by_id()
    if preset_id not in entries:
        raise ValueError(f"Неизвестный пресет: {preset_id}. Доступно: {', '.join(sorted(entries))}")
    return entries[preset_id]


def select_preset(
    preset_id: str,
    root: Path | None = None,
    workspace_id: str = "default",
    reason: str = "owner-selected-preset",
) -> StrategySelectionResult:
    """Совместимый выбор пресета; старое selection хранит поле strategyId."""

    return select_workspace_strategy(root=root, strategy_id=preset_id, profile_id=workspace_id, reason=reason)


def preset_catalog_to_text(root: Path | None = None) -> str:
    catalog = load_preset_catalog(root)
    lines = ["Zapret2 presets:"]
    for entry in catalog.entries:
        preset = entry.preset
        marker = " [selected]" if preset.preset_id == catalog.selected_preset_id else ""
        lines.append(f"  {preset.preset_id}{marker}: {preset.title}")
        lines.append(
            f"    profiles: {len(preset.profiles)}; global args: {len(preset.global_args)}; actions: {preset.action_count}"
        )
        lines.append(f"    service target: {entry.metadata.service_target_label}")
    return "\n".join(lines)


def preset_to_text(preset_id: str, root: Path | None = None) -> str:
    entry = load_preset(preset_id, root)
    preset = entry.preset
    issues = validate_preset(preset)
    lines = [
        f"Zapret2 preset: {preset.preset_id}",
        f"title: {preset.title}",
        f"source: {preset.source_path or 'legacy runtimeArgs'}",
        f"service target: {entry.metadata.service_target_label}",
        f"global args: {len(preset.global_args)}",
        f"profiles: {len(preset.profiles)}",
        "profile order: first match wins",
    ]
    for profile in preset.profiles:
        state = "enabled" if profile.enabled else "skipped"
        lines.extend(
            [
                f"  {profile.index + 1}. {profile.name} [{state}]",
                f"     id: {profile.profile_id}",
                f"     filter: {profile.traffic_filter.summary}",
                f"     strategy: {profile.strategy_label}",
                f"     range: {profile.range_label}",
                f"     direction: {profile.direction_label}",
            ]
        )
    if issues:
        lines.append("issues:")
        lines.extend(f"  - {issue.severity}: {issue.message}" for issue in issues)
    return "\n".join(lines)


def preset_profile_to_text(preset_id: str, profile_id: str, root: Path | None = None) -> str:
    preset = load_preset(preset_id, root).preset
    profiles = {profile.profile_id: profile for profile in preset.profiles}
    if profile_id not in profiles:
        # Разрешаем удобный порядковый номер из CLI.
        try:
            index = int(profile_id) - 1
        except ValueError:
            index = -1
        if not 0 <= index < len(preset.profiles):
            raise ValueError(f"Неизвестный профиль пресета: {profile_id}")
        profile = preset.profiles[index]
    else:
        profile = profiles[profile_id]
    return traffic_profile_to_text(preset, profile)


def traffic_profile_to_text(preset: ZapretPreset, profile: TrafficProfile) -> str:
    lines = [
        f"Preset profile: {preset.preset_id} / {profile.profile_id}",
        f"order: {profile.index + 1}",
        f"name: {profile.name}",
        f"enabled: {'yes' if profile.enabled else 'no'}",
        f"filter: {profile.traffic_filter.summary}",
        f"strategy: {profile.strategy_label}",
        f"range: {profile.range_label}",
        f"direction: {profile.direction_label}",
        "actions:",
    ]
    if profile.actions:
        for index, action in enumerate(profile.actions, 1):
            lines.append(
                f"  {index}. {action.function_name}; payload={action.payload}; "
                f"in={action.in_range}; out={action.out_range}; direction={action.direction}"
            )
    else:
        lines.append("  - нет")
    lines.append("raw args:")
    lines.extend(f"  - {arg}" for arg in profile.raw_args)
    return "\n".join(lines)
