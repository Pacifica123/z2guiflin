"""Общие исключения: домены и адреса, которые не трогает ни один профиль любого пресета.

Хранятся в ``.zap2/exclusions.json`` рабочего каталога и добавляются к профилям при сборке
плана запуска (``execution_plan.materialize_execution_plan``). Файлы пресетов не меняются:
исключения видны в плане и действуют для любого выбранного пресета.

Правило nfqws2 (desync.c dp_match): профиль с любым hostlist, даже только исключающим,
не выбирается, пока не известно имя хоста. Поэтому домены добавляются только в профили,
где уже есть список доменов; в профили по IP или «весь трафик» домены не ставятся —
иначе такие профили перестали бы обрабатывать первые пакеты соединения. Адреса
(``--ipset-exclude-ip``) такого правила не имеют и добавляются во все профили.
"""

from __future__ import annotations

from dataclasses import dataclass
import ipaddress
import json
import os
from pathlib import Path
from typing import Iterable

from ..models.preset import TrafficProfile, parse_preset_args
from ..models.profile_overlap import normalize_domain

FORMAT_VERSION = 1
_DOMAIN_LIST_PREFIXES = ("--hostlist=", "--hostlist-domains=", "--hostlist-auto=")
_FILTER_PREFIXES = (
    "--name=", "--skip", "--filter-", "--hostlist", "--ipset",
)
LOCAL_NETWORKS = (
    "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10", "169.254.0.0/16",
    "fc00::/7", "fe80::/10",
)


@dataclass(frozen=True)
class GlobalExclusions:
    domains: tuple[str, ...] = ()
    cidrs: tuple[str, ...] = ()

    @property
    def empty(self) -> bool:
        return not self.domains and not self.cidrs

    def to_dict(self) -> dict:
        return {"formatVersion": FORMAT_VERSION, "domains": list(self.domains), "cidrs": list(self.cidrs)}


def exclusions_path(root: Path) -> Path:
    return root / ".zap2" / "exclusions.json"


def _split(values: Iterable[str]) -> list[str]:
    result = []
    for value in values:
        for item in str(value).replace(",", " ").split():
            item = item.split("#", 1)[0].strip()
            if item:
                result.append(item)
    return result


def normalize_exclusions(domains: Iterable[str], cidrs: Iterable[str]) -> GlobalExclusions:
    clean_domains = []
    for raw in _split(domains):
        exact = raw.startswith("^")
        name = normalize_domain(raw[1:] if exact else raw)
        labels = name.split(".")
        if len(labels) < 2 or not all(label and len(label) <= 63 and all(ch.isalnum() or ch == "-" for ch in label) for label in labels):
            raise ValueError(f"не домен: {raw}")
        clean_domains.append(("^" if exact else "") + name)
    clean_cidrs = []
    for raw in _split(cidrs):
        try:
            network = ipaddress.ip_network(raw, strict=False)
        except ValueError as exc:
            raise ValueError(f"не IP/CIDR: {raw}") from exc
        if network.prefixlen == 0:
            raise ValueError(f"{raw} исключает весь интернет — чтобы выключить обход, остановите Default")
        clean_cidrs.append(str(network))
    return GlobalExclusions(tuple(dict.fromkeys(clean_domains)), tuple(dict.fromkeys(clean_cidrs)))


def load_global_exclusions(root: Path) -> GlobalExclusions:
    path = exclusions_path(root)
    if not path.is_file():
        return GlobalExclusions()
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("formatVersion") != FORMAT_VERSION:
        raise ValueError(f"{path}: неизвестный формат исключений")
    return normalize_exclusions(data.get("domains", ()), data.get("cidrs", ()))


def save_global_exclusions(root: Path, exclusions: GlobalExclusions) -> Path:
    path = exclusions_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(exclusions.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return path


def _has_domain_list(profile: TrafficProfile) -> bool:
    return bool(profile.traffic_filter.hostlist_domains or profile.traffic_filter.hostlists) or any(
        arg.startswith("--hostlist-auto=") for arg in profile.raw_args
    )


def _with_exclusions(raw_args: tuple[str, ...], extra: tuple[str, ...]) -> tuple[str, ...]:
    position = max((index + 1 for index, arg in enumerate(raw_args) if arg.startswith(_FILTER_PREFIXES)), default=0)
    return raw_args[:position] + extra + raw_args[position:]


def apply_global_exclusions(runtime_args: Iterable[str], exclusions: GlobalExclusions, preset_id: str = "plan") -> tuple[str, ...]:
    """argv пресета с общими исключениями в каждом подходящем профиле."""

    args = tuple(str(item) for item in runtime_args)
    if exclusions.empty:
        return args
    preset = parse_preset_args(args, preset_id=preset_id)
    if not preset.profiles:
        return args
    result: list[str] = list(preset.global_args)
    for profile in preset.profiles:
        extra: list[str] = []
        if exclusions.domains and _has_domain_list(profile):
            extra.append("--hostlist-exclude-domains=" + ",".join(exclusions.domains))
        if exclusions.cidrs:
            extra.append("--ipset-exclude-ip=" + ",".join(exclusions.cidrs))
        if profile.separator_arg:
            result.append(profile.separator_arg)
        result.extend(_with_exclusions(profile.raw_args, tuple(extra)))
    result.extend(preset.trailing_args)
    return tuple(result)


def exclusion_coverage(runtime_args: Iterable[str], exclusions: GlobalExclusions) -> tuple[int, int]:
    """Сколько профилей получат домены-исключения: (с доменами, всего)."""

    preset = parse_preset_args(tuple(runtime_args), preset_id="coverage")
    return sum(1 for profile in preset.profiles if _has_domain_list(profile)), len(preset.profiles)


__all__ = [
    "GlobalExclusions",
    "LOCAL_NETWORKS",
    "apply_global_exclusions",
    "exclusion_coverage",
    "exclusions_path",
    "load_global_exclusions",
    "normalize_exclusions",
    "save_global_exclusions",
]
