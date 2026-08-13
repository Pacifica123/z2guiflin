"""Поиск логического корня исходного пакета для импортируемых файлов.

Модуль не знает о пресетах как сущности. Он получает исходный файл и набор
безопасных относительных ссылок (например ``lists/youtube.txt``) и ищет
ближайший ancestor, от которого эти ссылки имеют смысл. Это позволяет одному
контракту обслуживать TXT preset сейчас и другие import adapters позже.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


MAX_SOURCE_PACKAGE_ANCESTORS = 10


@dataclass(frozen=True)
class SourcePackageRootProbe:
    root: Path
    resolved_refs: int
    total_refs: int
    marker_score: int
    reason: str

    @property
    def coverage(self) -> str:
        return f"{self.resolved_refs}/{self.total_refs}"


def _safe_relative_ref(value: str) -> Path | None:
    raw = str(value or "").strip().lstrip("@").replace("\\", "/")
    if not raw:
        return None
    candidate = Path(raw)
    if candidate.is_absolute() or ".." in candidate.parts:
        return None
    return candidate


def _source_ancestors(source: Path) -> tuple[Path, ...]:
    current = source.expanduser().resolve().parent
    result: list[Path] = []
    for _ in range(MAX_SOURCE_PACKAGE_ANCESTORS):
        if current not in result:
            result.append(current)
        if current.parent == current:
            break
        current = current.parent
    return tuple(result)


def _marker_score(root: Path) -> tuple[int, str]:
    score = 0
    labels: list[str] = []
    markers = (
        ("presets", 4),
        ("lists", 4),
        ("lua", 2),
        ("bin", 2),
        ("windivert.filter", 1),
    )
    for name, weight in markers:
        if (root / name).exists():
            score += weight
            labels.append(name)

    # loop-uh/Zapret GUI source checkout: ``src`` является тем же логическим
    # resource root, который после упаковки становится application root.
    if (root / "config/runtime_layout.py").is_file() and (root / "presets/builtin").is_dir():
        score += 8
        labels.append("application-resource-root")
    if (root / "src/config/runtime_layout.py").is_file() and (root / "src/presets/builtin").is_dir():
        score += 3
        labels.append("source-repository-root")
    return score, ",".join(labels) or "ancestor"


def probe_source_package_roots(
    source_file: Path | str,
    relative_refs: Iterable[str] = (),
    *,
    explicit_root: Path | str | None = None,
) -> tuple[SourcePackageRootProbe, ...]:
    """Вернуть кандидатов package root в порядке полезности.

    ``explicit_root`` всегда идёт первым: пользовательский выбор имеет приоритет,
    но автоматические ancestors остаются fallback для частичных пакетов.
    """

    source = Path(source_file).expanduser().resolve()
    refs: list[Path] = []
    for value in relative_refs:
        ref = _safe_relative_ref(str(value))
        if ref is not None and ref not in refs:
            refs.append(ref)

    roots: list[Path] = []
    explicit: Path | None = None
    if explicit_root is not None:
        explicit = Path(explicit_root).expanduser().resolve()
        roots.append(explicit)
    for ancestor in _source_ancestors(source):
        if ancestor not in roots:
            roots.append(ancestor)

    probes: list[SourcePackageRootProbe] = []
    for root in roots:
        resolved = sum(1 for ref in refs if (root / ref).is_file())
        marker_score, marker_reason = _marker_score(root)
        reason = "explicit" if explicit is not None and root == explicit else marker_reason
        probes.append(
            SourcePackageRootProbe(
                root=root,
                resolved_refs=resolved,
                total_refs=len(refs),
                marker_score=marker_score,
                reason=reason,
            )
        )

    if explicit is not None:
        explicit_probe = probes[0]
        automatic = sorted(
            probes[1:],
            key=lambda item: (item.resolved_refs, item.marker_score, -len(item.root.parts)),
            reverse=True,
        )
        return (explicit_probe, *automatic)
    return tuple(
        sorted(
            probes,
            key=lambda item: (item.resolved_refs, item.marker_score, -len(item.root.parts)),
            reverse=True,
        )
    )


def discover_source_package_root(
    source_file: Path | str,
    relative_refs: Iterable[str] = (),
    *,
    explicit_root: Path | str | None = None,
) -> SourcePackageRootProbe | None:
    probes = probe_source_package_roots(source_file, relative_refs, explicit_root=explicit_root)
    if not probes:
        return None
    if explicit_root is not None:
        return probes[0]
    best = probes[0]
    # Не называем случайный ancestor корнем пакета только потому, что он есть.
    if best.resolved_refs <= 0 and best.marker_score <= 0:
        return None
    return best


def resolve_source_package_file(
    source_file: Path | str,
    relative_ref: str,
    *,
    explicit_root: Path | str | None = None,
    all_relative_refs: Iterable[str] = (),
) -> tuple[Path | None, SourcePackageRootProbe | None]:
    """Найти один companion file через общий package-root resolver."""

    ref = _safe_relative_ref(relative_ref)
    if ref is None:
        return None, None
    probes = probe_source_package_roots(
        source_file,
        tuple(all_relative_refs) or (relative_ref,),
        explicit_root=explicit_root,
    )
    for probe in probes:
        candidate = (probe.root / ref).resolve()
        try:
            candidate.relative_to(probe.root)
        except ValueError:
            continue
        if candidate.is_file():
            return candidate, probe
    return None, (probes[0] if probes else None)
