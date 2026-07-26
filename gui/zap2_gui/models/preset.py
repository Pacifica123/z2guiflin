"""Модель Zapret2: пресет состоит из глобальных опций и traffic-профилей.

Модуль не запускает nfqws2 и не меняет файлы. Он только разбирает уже
подготовленный argv в прозрачную структуру и умеет собрать его обратно без
изменений.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import re
from pathlib import Path
from typing import Iterable


_PROFILE_PREFIXES = (
    "--skip",
    "--name",
    "--template",
    "--import",
    "--cookie",
    "--filter-",
    "--hostlist=",
    "--hostlist-domains=",
    "--hostlist-exclude=",
    "--hostlist-exclude-domains=",
    "--hostlist-auto=",
    "--ipset=",
    "--ipset-ip=",
    "--ipset-exclude=",
    "--ipset-exclude-ip=",
    "--payload=",
    "--in-range",
    "--out-range",
    "--lua-desync=",
)

_MATCH_PREFIXES = (
    "--filter-",
    "--hostlist=",
    "--hostlist-domains=",
    "--hostlist-exclude=",
    "--hostlist-exclude-domains=",
    "--hostlist-auto=",
    "--ipset=",
    "--ipset-ip=",
    "--ipset-exclude=",
    "--ipset-exclude-ip=",
)


def _option_value(arg: str) -> str:
    return arg.partition("=")[2] if "=" in arg else ""


def _is_new(arg: str) -> bool:
    return arg == "--new" or arg.startswith("--new=")


def _is_profile_arg(arg: str) -> bool:
    return _is_new(arg) or arg.startswith(_PROFILE_PREFIXES)


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9а-яё]+", "-", value.lower(), flags=re.IGNORECASE).strip("-")
    return cleaned[:48] or "profile"


def _direction_from_ranges(in_range: str, out_range: str) -> str:
    in_enabled = in_range != "x"
    out_enabled = out_range != "x"
    if in_enabled and out_enabled:
        return "any"
    if in_enabled:
        return "in"
    if out_enabled:
        return "out"
    return "none"


@dataclass(frozen=True)
class PresetAction:
    """Один --lua-desync с действующими перед ним range/payload."""

    raw_arg: str
    function_name: str
    payload: str
    in_range: str
    out_range: str
    direction: str

    @property
    def range_label(self) -> str:
        return f"in={self.in_range}; out={self.out_range}"


@dataclass(frozen=True)
class TrafficFilter:
    """Профильные фильтры, по которым nfqws2 выбирает первый подходящий блок."""

    raw_args: tuple[str, ...]
    tcp: tuple[str, ...]
    udp: tuple[str, ...]
    l3: tuple[str, ...]
    l7: tuple[str, ...]
    hostlists: tuple[str, ...]
    hostlist_domains: tuple[str, ...]
    ipsets: tuple[str, ...]
    inline_ips: tuple[str, ...]

    @property
    def summary(self) -> str:
        parts: list[str] = []
        if self.tcp:
            parts.append("TCP " + ",".join(self.tcp))
        if self.udp:
            parts.append("UDP " + ",".join(self.udp))
        if self.l7:
            parts.append("L7 " + ",".join(self.l7))
        if self.hostlist_domains:
            domains = list(self.hostlist_domains)
            shown = ", ".join(domains[:2])
            if len(domains) > 2:
                shown += f" +{len(domains) - 2}"
            parts.append(shown)
        elif self.hostlists:
            parts.append("hostlist " + ", ".join(Path(item).name for item in self.hostlists))
        if self.inline_ips:
            parts.append(f"IP/CIDR: {len(self.inline_ips)}")
        elif self.ipsets:
            parts.append("ipset " + ", ".join(Path(item).name for item in self.ipsets))
        return " · ".join(parts) or "любой трафик"


@dataclass(frozen=True)
class TrafficProfile:
    """Один рабочий блок пресета, отделённый от следующего через --new."""

    profile_id: str
    index: int
    name: str
    enabled: bool
    separator_arg: str | None
    raw_args: tuple[str, ...]
    traffic_filter: TrafficFilter
    actions: tuple[PresetAction, ...]

    @property
    def strategy_label(self) -> str:
        names: list[str] = []
        for action in self.actions:
            if action.function_name not in names:
                names.append(action.function_name)
        return " + ".join(names) if names else "pass (ничего не делает)"

    @property
    def direction_label(self) -> str:
        values = tuple(dict.fromkeys(action.direction for action in self.actions))
        if not values:
            return "out (по умолчанию)"
        return values[0] if len(values) == 1 else "/".join(values)

    @property
    def range_label(self) -> str:
        values = tuple(dict.fromkeys((action.in_range, action.out_range) for action in self.actions))
        if not values:
            return "in=x; out=a"
        if len(values) == 1:
            return f"in={values[0][0]}; out={values[0][1]}"
        return f"{len(values)} набора range"


@dataclass(frozen=True)
class ZapretPreset:
    """Исполнимый пресет nfqws2 и его упорядоченные профили."""

    preset_id: str
    title: str
    engine: str
    global_args: tuple[str, ...]
    profiles: tuple[TrafficProfile, ...]
    trailing_args: tuple[str, ...] = ()
    source_path: str = ""

    def to_runtime_args(self) -> tuple[str, ...]:
        args: list[str] = list(self.global_args)
        for profile in self.profiles:
            if profile.separator_arg:
                args.append(profile.separator_arg)
            args.extend(profile.raw_args)
        args.extend(self.trailing_args)
        return tuple(args)

    @property
    def action_count(self) -> int:
        return sum(len(profile.actions) for profile in self.profiles)


@dataclass(frozen=True)
class PresetParseIssue:
    severity: str
    message: str


def _split_values(arg: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in _option_value(arg).split(",") if item.strip())


def _build_filter(args: tuple[str, ...]) -> TrafficFilter:
    match_args = tuple(arg for arg in args if arg.startswith(_MATCH_PREFIXES))
    return TrafficFilter(
        raw_args=match_args,
        tcp=tuple(value for arg in args if arg.startswith("--filter-tcp=") for value in _split_values(arg)),
        udp=tuple(value for arg in args if arg.startswith("--filter-udp=") for value in _split_values(arg)),
        l3=tuple(value for arg in args if arg.startswith("--filter-l3=") for value in _split_values(arg)),
        l7=tuple(value for arg in args if arg.startswith("--filter-l7=") for value in _split_values(arg)),
        hostlists=tuple(_option_value(arg) for arg in args if arg.startswith("--hostlist=")),
        hostlist_domains=tuple(
            value
            for arg in args
            if arg.startswith("--hostlist-domains=")
            for value in _split_values(arg)
        ),
        ipsets=tuple(_option_value(arg) for arg in args if arg.startswith("--ipset=")),
        inline_ips=tuple(
            value
            for arg in args
            if arg.startswith("--ipset-ip=")
            for value in _split_values(arg)
        ),
    )


def _action_direction(raw_action: str, in_range: str, out_range: str) -> str:
    value = _option_value(raw_action)
    for part in value.split(":")[1:]:
        if part.startswith("dir="):
            explicit = part.partition("=")[2].strip().lower()
            if explicit in {"in", "out", "any"}:
                return explicit
    return _direction_from_ranges(in_range, out_range)


def _build_actions(args: tuple[str, ...]) -> tuple[PresetAction, ...]:
    payload = "all"
    in_range = "x"
    out_range = "a"
    actions: list[PresetAction] = []
    for arg in args:
        if arg.startswith("--payload="):
            payload = _option_value(arg) or "all"
        elif arg.startswith("--in-range="):
            in_range = _option_value(arg) or "x"
        elif arg.startswith("--out-range="):
            out_range = _option_value(arg) or "a"
        elif arg.startswith("--lua-desync="):
            raw_value = _option_value(arg)
            function_name = raw_value.split(":", 1)[0].strip() or "unknown"
            actions.append(
                PresetAction(
                    raw_arg=arg,
                    function_name=function_name,
                    payload=payload,
                    in_range=in_range,
                    out_range=out_range,
                    direction=_action_direction(arg, in_range, out_range),
                )
            )
    return tuple(actions)


def _explicit_name(separator_arg: str | None, args: tuple[str, ...]) -> str:
    if separator_arg and separator_arg.startswith("--new="):
        value = _option_value(separator_arg).strip()
        if value:
            return value
    for arg in args:
        if arg.startswith("--name="):
            value = _option_value(arg).strip()
            if value:
                return value
    return ""


def _inferred_name(index: int, traffic_filter: TrafficFilter, actions: tuple[PresetAction, ...]) -> str:
    domains = {item.lower() for item in traffic_filter.hostlist_domains}
    funcs = {action.function_name for action in actions}
    if any("youtube" in item or "googlevideo" in item or "ytimg" in item for item in domains):
        return "YouTube QUIC" if traffic_filter.udp else "YouTube"
    if any("discord.media" in item for item in domains):
        return "Discord media"
    if any("discord" in item for item in domains):
        return "Discord app/CDN"
    if traffic_filter.inline_ips and ("syndata" in funcs or "wssize" in funcs):
        return "Edge / начало соединения"
    if traffic_filter.tcp:
        return "TCP " + ",".join(traffic_filter.tcp)
    if traffic_filter.udp and any("quic" in action.raw_arg.lower() for action in actions):
        return "QUIC / UDP " + ",".join(traffic_filter.udp)
    if traffic_filter.udp:
        return "UDP " + ",".join(traffic_filter.udp)
    return f"Профиль {index + 1}"


def _build_profile_id(
    preset_id: str,
    name: str,
    traffic_filter: TrafficFilter,
    raw_args: tuple[str, ...],
    used: set[str],
) -> str:
    signature = "\0".join(traffic_filter.raw_args or raw_args)
    base = _slug(name) if name else sha256(signature.encode("utf-8")).hexdigest()[:10]
    candidate = f"{preset_id}:{base}"
    suffix = 2
    while candidate in used:
        candidate = f"{preset_id}:{base}-{suffix}"
        suffix += 1
    used.add(candidate)
    return candidate


def parse_preset_args(
    args: Iterable[str],
    *,
    preset_id: str,
    title: str = "",
    engine: str = "nfqws2",
    source_path: str = "",
) -> ZapretPreset:
    """Разобрать argv пресета и сохранить возможность точного round-trip."""

    raw = tuple(str(arg).strip() for arg in args if str(arg).strip())
    first_profile = next((index for index, arg in enumerate(raw) if _is_profile_arg(arg)), len(raw))
    global_args = raw[:first_profile]
    body = raw[first_profile:]
    if not body:
        return ZapretPreset(
            preset_id=preset_id,
            title=title or preset_id,
            engine=engine,
            global_args=global_args,
            profiles=(),
            source_path=source_path,
        )

    raw_profiles: list[tuple[str | None, tuple[str, ...]]] = []
    current: list[str] = []
    separator: str | None = None
    trailing: tuple[str, ...] = ()
    for arg in body:
        if _is_new(arg):
            if current:
                raw_profiles.append((separator, tuple(current)))
                current = []
            elif separator is not None:
                raw_profiles.append((separator, ()))
            separator = arg
            continue
        current.append(arg)
    if current:
        raw_profiles.append((separator, tuple(current)))
    elif separator is not None:
        trailing = (separator,)

    profiles: list[TrafficProfile] = []
    used_ids: set[str] = set()
    for index, (profile_separator, profile_args) in enumerate(raw_profiles):
        traffic_filter = _build_filter(profile_args)
        actions = _build_actions(profile_args)
        explicit_name = _explicit_name(profile_separator, profile_args)
        display_name = explicit_name or _inferred_name(index, traffic_filter, actions)
        profiles.append(
            TrafficProfile(
                profile_id=_build_profile_id(preset_id, explicit_name, traffic_filter, profile_args, used_ids),
                index=index,
                name=display_name,
                enabled="--skip" not in profile_args,
                separator_arg=profile_separator,
                raw_args=profile_args,
                traffic_filter=traffic_filter,
                actions=actions,
            )
        )

    return ZapretPreset(
        preset_id=preset_id,
        title=title or preset_id,
        engine=engine,
        global_args=global_args,
        profiles=tuple(profiles),
        trailing_args=trailing,
        source_path=source_path,
    )


def validate_preset(preset: ZapretPreset) -> tuple[PresetParseIssue, ...]:
    issues: list[PresetParseIssue] = []
    if preset.to_runtime_args() and not preset.profiles:
        issues.append(PresetParseIssue("warning", f"Пресет {preset.preset_id} содержит только глобальные опции"))
    if len({profile.profile_id for profile in preset.profiles}) != len(preset.profiles):
        issues.append(PresetParseIssue("error", f"В пресете {preset.preset_id} повторяются profile id"))
    for profile in preset.profiles:
        if not profile.traffic_filter.raw_args:
            issues.append(
                PresetParseIssue(
                    "warning",
                    f"Профиль {profile.name} не имеет явного filter и может перехватить трафик раньше следующих профилей",
                )
            )
    return tuple(issues)
