"""Безопасный импорт line-oriented ``.txt`` пресетов Zapret2.

Импорт не запускает nfqws2 и не меняет nftables. Windows capture options и
runtime-owned flags не переносятся в canonical preset. Доступные bundled Lua и
blob resources переписываются на пути vendored Linux core.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256
from pathlib import Path
import re
from typing import Iterable

from .preset_editor import PresetMutationResult, create_owner_preset_from_runtime_args
from .strategy_file_inputs import split_strategy_file_arg
from ..models.preset import ZapretPreset, parse_preset_args
from ..project_paths import discover_layout


MAX_PRESET_TEXT_BYTES = 4 * 1024 * 1024

_WINDOWS_ONLY_PREFIXES = (
    "--wf-",
)
_RUNTIME_OWNED_PREFIXES = (
    "--qnum",
    "--daemon",
    "--pidfile",
    "--user",
    "--uid",
    "--gid",
    "--dry-run",
)
_ZAPRET1_PREFIXES = (
    "--dpi-desync",
    "--dpi-desync-fooling",
    "--dpi-desync-repeats",
    "--dpi-desync-split",
    "--dpi-desync-any-protocol",
)
_LIST_PREFIXES = (
    "--hostlist=",
    "--hostlist-exclude=",
    "--hostlist-auto=",
    "--ipset=",
    "--ipset-exclude=",
)
_METADATA_RE = re.compile(r"^\s*#\s*([^:]+)\s*:\s*(.*?)\s*$")
_FUNCTION_RE = re.compile(r"^\s*function\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", re.MULTILINE)
_BLOB_REF_RE = re.compile(r"(?:^|:)blob=([A-Za-z0-9_.-]+)(?::|$)")


@dataclass(frozen=True)
class PresetTxtImportIssue:
    severity: str
    code: str
    message: str


@dataclass(frozen=True)
class PresetTxtImportAnalysis:
    source_path: Path
    encoding: str
    title: str
    builtin_version: str
    description: str
    source_sha256: str
    source_args: tuple[str, ...]
    runtime_args: tuple[str, ...]
    parsed_preset: ZapretPreset
    confidence: str
    adaptations: tuple[str, ...]
    issues: tuple[PresetTxtImportIssue, ...]
    windows_tcp_capture_hint: tuple[str, ...] = ()
    windows_udp_capture_hint: tuple[str, ...] = ()
    missing_list_dependencies: tuple[str, ...] = ()
    external_list_dependencies: tuple[str, ...] = ()

    @property
    def errors(self) -> tuple[PresetTxtImportIssue, ...]:
        return tuple(item for item in self.issues if item.severity == "error")

    @property
    def warnings(self) -> tuple[PresetTxtImportIssue, ...]:
        return tuple(item for item in self.issues if item.severity == "warning")

    @property
    def can_import(self) -> bool:
        return bool(self.runtime_args) and bool(self.parsed_preset.profiles) and not self.errors

    @property
    def runtime_ready_after_import(self) -> bool:
        return self.can_import and not self.missing_list_dependencies

    def to_text(self) -> str:
        lines = [
            "TXT preset import analysis",
            f"source: {self.source_path}",
            f"encoding: {self.encoding}",
            f"title: {self.title}",
            f"confidence: {self.confidence}",
            f"source args: {len(self.source_args)}",
            f"runtime args after adaptation: {len(self.runtime_args)}",
            f"profiles: {len(self.parsed_preset.profiles)}",
            f"actions: {self.parsed_preset.action_count}",
            f"can import: {'yes' if self.can_import else 'no'}",
            f"runtime ready after import: {'yes' if self.runtime_ready_after_import else 'no'}",
            "executes nfqws2 now: no",
            "mutates firewall/services now: no",
        ]
        if self.builtin_version:
            lines.append(f"source BuiltinVersion: {self.builtin_version}")
        if self.description:
            lines.append(f"description: {self.description}")
        if self.windows_tcp_capture_hint:
            lines.append("removed Windows TCP capture hint: " + ",".join(self.windows_tcp_capture_hint))
        if self.windows_udp_capture_hint:
            lines.append("removed Windows UDP capture hint: " + ",".join(self.windows_udp_capture_hint))
        if self.external_list_dependencies:
            lines.append(f"external list/ipset files ready to copy: {len(self.external_list_dependencies)}")
        if self.missing_list_dependencies:
            lines.append("missing list/ipset files: " + ", ".join(self.missing_list_dependencies))
        if self.adaptations:
            lines.append("adaptations:")
            lines.extend(f"  - {item}" for item in self.adaptations)
        if self.issues:
            lines.append("issues:")
            lines.extend(f"  - {item.severity}/{item.code}: {item.message}" for item in self.issues)
        return "\n".join(lines)


@dataclass(frozen=True)
class PresetTxtImportResult:
    mutation: PresetMutationResult
    analysis: PresetTxtImportAnalysis

    @property
    def preset_id(self) -> str:
        return self.mutation.preset_id

    def to_text(self) -> str:
        return self.analysis.to_text() + "\n\n" + self.mutation.to_text()


def _decode_preset_bytes(raw: bytes) -> tuple[str, str]:
    if len(raw) > MAX_PRESET_TEXT_BYTES:
        raise ValueError(f"TXT preset слишком большой: {len(raw)} bytes; limit={MAX_PRESET_TEXT_BYTES}")
    if b"\x00" in raw:
        raise ValueError("Файл содержит NUL bytes и не похож на текстовый preset")
    for encoding in ("utf-8-sig", "cp1251"):
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    raise ValueError("TXT preset не удалось декодировать как UTF-8 или CP1251")


def _metadata_from_text(text: str) -> dict[str, str]:
    metadata: dict[str, str] = {}
    for raw_line in text.splitlines()[:80]:
        match = _METADATA_RE.match(raw_line)
        if not match:
            continue
        key = match.group(1).strip().lower()
        value = match.group(2).strip()
        if key and value and key not in metadata:
            metadata[key] = value
    return metadata


def _logical_lines(text: str) -> tuple[str, ...]:
    """Собрать line-oriented config, поддерживая обычный ``\\`` continuation."""

    result: list[str] = []
    pending = ""
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith(";"):
            continue
        if pending:
            line = pending + line
            pending = ""
        if line.endswith("\\") and not line.endswith("\\\\"):
            pending = line[:-1].rstrip() + " "
            continue
        result.append(line)
    if pending.strip():
        result.append(pending.strip())
    return tuple(result)


def _strategy_confidence(lines: tuple[str, ...]) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
    option_lines = tuple(line for line in lines if line.startswith("--"))
    other_lines = tuple(line for line in lines if not line.startswith("--"))
    lua_actions = sum(line.startswith("--lua-desync=") for line in option_lines)
    zapret1_actions = sum(line.startswith("--dpi-desync") for line in option_lines)
    filters = sum(
        line.startswith(("--filter-", "--hostlist", "--ipset", "--payload="))
        for line in option_lines
    )
    separators = sum(line == "--new" or line.startswith("--new=") for line in option_lines)
    globals_count = sum(line.startswith(("--lua-init=", "--blob=", "--ctrack-", "--ipcache-", "--wf-")) for line in option_lines)
    score = lua_actions * 6 + zapret1_actions * 5 + min(filters, 5) * 2 + min(separators, 3) * 2 + min(globals_count, 3)

    if len(option_lines) < 2 or score < 6 or (lua_actions + zapret1_actions == 0 and filters < 2):
        confidence = "not-a-preset"
    elif score >= 20 and not other_lines:
        confidence = "high"
    elif score >= 12 and len(other_lines) <= 1:
        confidence = "medium"
    else:
        confidence = "low"
    return confidence, option_lines, other_lines


def _csv_value(arg: str) -> tuple[str, ...]:
    value = arg.partition("=")[2]
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _matches_option(arg: str, name: str) -> bool:
    return arg == name or arg.startswith(name + "=")


def _unsafe_workspace_file_ref(value: str) -> bool:
    raw = value.lstrip("@").replace("\\", "/")
    path = Path(raw)
    return path.is_absolute() or ".." in path.parts


def _project_resource_arg(root: Path, source_value: str, *, kind: str) -> tuple[str | None, str | None]:
    """Вернуть project-relative @path и описание adaptation, если resource есть."""

    if not source_value.startswith("@"):
        return source_value, None
    raw_path = source_value[1:].replace("\\", "/")
    candidates: list[Path] = []
    if kind == "lua":
        if raw_path.startswith("lua/"):
            candidates.append(root / "core/zapret2/lua" / raw_path.removeprefix("lua/"))
        if raw_path.startswith("core/zapret2/lua/"):
            candidates.append(root / raw_path)
        candidates.append(root / "core/zapret2/lua" / Path(raw_path).name)
    elif kind == "blob":
        if raw_path.startswith("bin/"):
            candidates.append(root / "core/zapret2/files/fake" / raw_path.removeprefix("bin/"))
        if raw_path.startswith("files/fake/"):
            candidates.append(root / "core/zapret2" / raw_path)
        if raw_path.startswith("core/zapret2/files/fake/"):
            candidates.append(root / raw_path)
        candidates.append(root / "core/zapret2/files/fake" / Path(raw_path).name)
    for candidate in candidates:
        if candidate.is_file():
            rel = candidate.relative_to(root).as_posix()
            mapped = f"@{rel}"
            note = None if mapped == source_value else f"resource path: {source_value} -> {mapped}"
            return mapped, note
    return None, None


def _loaded_lua_functions(root: Path, lua_init_args: Iterable[str]) -> set[str]:
    functions: set[str] = set()
    for arg in lua_init_args:
        if not arg.startswith("--lua-init=@"):
            continue
        rel = arg.partition("=@")[2]
        path = root / rel
        if not path.is_file():
            continue
        try:
            functions.update(_FUNCTION_RE.findall(path.read_text(encoding="utf-8")))
        except (OSError, UnicodeDecodeError):
            continue
    return functions


def _used_desync_functions(args: Iterable[str]) -> set[str]:
    result: set[str] = set()
    for arg in args:
        if not arg.startswith("--lua-desync="):
            continue
        value = arg.partition("=")[2]
        name = value.split(":", 1)[0].strip()
        if name:
            result.add(name)
    return result


def _used_blob_names(args: Iterable[str]) -> set[str]:
    names: set[str] = set()
    for arg in args:
        if not arg.startswith("--lua-desync="):
            continue
        for match in _BLOB_REF_RE.finditer(arg.partition("=")[2]):
            names.add(match.group(1))
    return names


def _list_reference_value(arg: str) -> str:
    return arg.partition("=")[2].strip()



def _dependency_search_roots(source: Path, dependency_root: Path | None = None) -> tuple[Path, ...]:
    roots: list[Path] = []
    if dependency_root is not None:
        roots.append(Path(dependency_root).expanduser().resolve())
    current = source.parent.resolve()
    for _ in range(3):
        if current not in roots:
            roots.append(current)
        if current.parent == current:
            break
        current = current.parent
    return tuple(roots)


def _external_list_source(source: Path, value: str, dependency_root: Path | None = None) -> Path | None:
    raw = value.lstrip("@").replace("\\", "/").strip()
    if not raw or _unsafe_workspace_file_ref(raw):
        return None
    rel = Path(raw)
    candidates: list[Path] = []
    for base in _dependency_search_roots(source, dependency_root):
        candidates.append(base / rel)
        if rel.parts and base.name == rel.parts[0] and len(rel.parts) > 1:
            candidates.append(base.joinpath(*rel.parts[1:]))
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if resolved.is_file():
            return resolved
    return None


def _materialize_list_dependencies(
    analysis: PresetTxtImportAnalysis,
    root: Path,
    dependency_root: Path | None,
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    """Copy source-package list/ipset inputs into immutable project-owned assets."""

    external: dict[tuple[str, str], Path] = {}
    unresolved: list[str] = []
    for arg in analysis.runtime_args:
        parsed = split_strategy_file_arg(arg)
        if parsed is None:
            continue
        option, value = parsed
        project_candidate = root / value.lstrip("@").replace("\\", "/")
        if project_candidate.is_file():
            continue
        source_path = _external_list_source(analysis.source_path, value, dependency_root)
        if source_path is None:
            if value not in unresolved:
                unresolved.append(value)
            continue
        external[(option, value)] = source_path

    if not external:
        return analysis.runtime_args, (), tuple(unresolved), ()

    digest = sha256()
    digest.update(analysis.source_sha256.encode("ascii"))
    for (option, value), source_path in sorted(external.items()):
        digest.update(option.encode("utf-8"))
        digest.update(b"\0")
        digest.update(value.encode("utf-8"))
        digest.update(b"\0")
        digest.update(sha256(source_path.read_bytes()).digest())
    asset_rel_root = Path("presets/imported-assets") / f"txt-{digest.hexdigest()[:16]}"
    asset_root = root / asset_rel_root

    target_by_key: dict[tuple[str, str], Path] = {}
    copied_notes: list[str] = []
    for key, source_path in external.items():
        _option, value = key
        rel = Path(value.lstrip("@").replace("\\", "/"))
        target = asset_root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = source_path.read_bytes()
        if target.exists():
            if target.read_bytes() != payload:
                raise ValueError(f"Конфликт imported list asset: {target}")
        else:
            tmp = target.with_suffix(target.suffix + ".tmp")
            tmp.write_bytes(payload)
            tmp.replace(target)
        target_by_key[key] = target
        copied_notes.append(f"list asset: {value} -> {target.relative_to(root).as_posix()}")

    rewritten: list[str] = []
    for arg in analysis.runtime_args:
        parsed = split_strategy_file_arg(arg)
        if parsed is None or parsed not in target_by_key:
            rewritten.append(arg)
            continue
        option, _value = parsed
        target = target_by_key[parsed]
        rewritten.append(f"{option}={target.relative_to(root).as_posix()}")

    return tuple(rewritten), tuple(copied_notes), tuple(unresolved), (asset_rel_root.as_posix(),)


def analyze_txt_preset(path: Path | str, root: Path | None = None, dependency_root: Path | None = None) -> PresetTxtImportAnalysis:
    layout = discover_layout(root)
    source = Path(path).expanduser().resolve()
    if source.suffix.lower() != ".txt":
        raise ValueError("Импорт полного пресета принимает только .txt")
    if not source.is_file():
        raise ValueError(f"TXT preset не найден: {source}")
    raw = source.read_bytes()
    text, encoding = _decode_preset_bytes(raw)
    metadata = _metadata_from_text(text)
    logical = _logical_lines(text)
    confidence, source_args, other_lines = _strategy_confidence(logical)
    if confidence == "not-a-preset":
        raise ValueError(
            "Файл не распознан как Zapret preset: недостаточно filter/desync/new/lua-init признаков"
        )
    if other_lines:
        preview = "; ".join(other_lines[:3])
        raise ValueError(f"В preset найдены непонятные строки без '--': {preview}")

    issues: list[PresetTxtImportIssue] = []
    adaptations: list[str] = []
    adapted: list[str] = []
    missing_lua: list[str] = []
    dropped_blob_defs: dict[str, str] = {}
    tcp_hint: list[str] = []
    udp_hint: list[str] = []

    for arg in source_args:
        if arg.startswith(_ZAPRET1_PREFIXES):
            issues.append(
                PresetTxtImportIssue(
                    "error",
                    "ZAPRET1_OPTION_UNSUPPORTED",
                    f"{arg.split('=', 1)[0]} относится к zapret1/winws и не переводится автоматически в nfqws2 Lua",
                )
            )
            continue
        if arg.startswith("--wf-tcp-out="):
            tcp_hint.extend(item for item in _csv_value(arg) if item not in tcp_hint)
            adaptations.append(f"удалён WinDivert capture option: {arg}")
            continue
        if arg.startswith("--wf-udp-out="):
            udp_hint.extend(item for item in _csv_value(arg) if item not in udp_hint)
            adaptations.append(f"удалён WinDivert capture option: {arg}")
            continue
        if arg.startswith(_WINDOWS_ONLY_PREFIXES):
            adaptations.append(f"удалён Windows-only option: {arg}")
            continue
        if any(_matches_option(arg, name) for name in _RUNTIME_OWNED_PREFIXES):
            adaptations.append(f"удалён runtime-owned option: {arg}")
            continue
        if arg.startswith("--lua-init="):
            value = arg.partition("=")[2]
            mapped, note = _project_resource_arg(layout.root, value, kind="lua")
            if mapped is None:
                missing_lua.append(value)
                adaptations.append(f"пропущен отсутствующий Lua init: {value}")
                continue
            new_arg = f"--lua-init={mapped}"
            if note:
                adaptations.append(note)
            if new_arg not in adapted:
                adapted.append(new_arg)
            continue
        if arg.startswith("--blob="):
            payload = arg.partition("=")[2]
            name, sep, value = payload.partition(":")
            if not sep or not name:
                adapted.append(arg)
                continue
            if value.startswith("@"):
                mapped, note = _project_resource_arg(layout.root, value, kind="blob")
                if mapped is None:
                    dropped_blob_defs[name] = value
                    adaptations.append(f"пропущен отсутствующий blob {name}: {value}")
                    continue
                new_arg = f"--blob={name}:{mapped}"
                if note:
                    adaptations.append(note)
                adapted.append(new_arg)
            else:
                adapted.append(arg)
            continue
        if arg.startswith(_LIST_PREFIXES):
            value = _list_reference_value(arg)
            if _unsafe_workspace_file_ref(value):
                issues.append(
                    PresetTxtImportIssue(
                        "error",
                        "UNSAFE_FILE_REFERENCE",
                        f"File reference выходит за пределы workspace и не импортируется: {value}",
                    )
                )
                continue
        adapted.append(arg)

    # zapret2 txt из некоторых GUI может полагаться на стандартные Lua scripts
    # неявно. Для owner-managed Linux preset они должны быть явными.
    if any(arg.startswith("--lua-desync=") for arg in adapted):
        required = (
            "--lua-init=@core/zapret2/lua/zapret-lib.lua",
            "--lua-init=@core/zapret2/lua/zapret-antidpi.lua",
        )
        injected: list[str] = []
        for item in required:
            if item not in adapted:
                injected.append(item)
                adaptations.append(f"добавлен обязательный Linux Lua init: {item.partition('=')[2]}")
        if injected:
            adapted = injected + adapted

    used_functions = _used_desync_functions(adapted)
    loaded_functions = _loaded_lua_functions(layout.root, (arg for arg in adapted if arg.startswith("--lua-init=")))
    missing_functions = sorted(used_functions - loaded_functions)
    if missing_functions:
        issues.append(
            PresetTxtImportIssue(
                "error",
                "LUA_DESYNC_FUNCTION_UNAVAILABLE",
                "В загруженных vendored Lua scripts нет функций: " + ", ".join(missing_functions),
            )
        )
    elif missing_lua:
        issues.append(
            PresetTxtImportIssue(
                "warning",
                "UNUSED_LUA_INIT_DROPPED",
                "Отсутствующие Lua init удалены; все реально используемые --lua-desync функции найдены в оставшихся scripts: "
                + ", ".join(missing_lua),
            )
        )

    used_blobs = _used_blob_names(adapted)
    missing_used_blobs = sorted(name for name in dropped_blob_defs if name in used_blobs)
    if missing_used_blobs:
        issues.append(
            PresetTxtImportIssue(
                "error",
                "USED_BLOB_UNAVAILABLE",
                "Профили используют blob definitions, файлов которых нет в vendored core: " + ", ".join(missing_used_blobs),
            )
        )
    dropped_unused = sorted(name for name in dropped_blob_defs if name not in used_blobs)
    if dropped_unused:
        issues.append(
            PresetTxtImportIssue(
                "warning",
                "UNUSED_BLOB_DEFINITIONS_DROPPED",
                "Удалены отсутствующие blob definitions, на которые адаптированные lua-desync не ссылаются: "
                + ", ".join(dropped_unused),
            )
        )

    missing_lists: list[str] = []
    external_lists: list[str] = []
    for arg in adapted:
        parsed_list = split_strategy_file_arg(arg)
        if parsed_list is None:
            continue
        _option, value = parsed_list
        normalized = value.lstrip("@").replace("\\", "/")
        candidate = layout.root / normalized
        if not value or candidate.is_file():
            continue
        if _external_list_source(source, value, dependency_root) is not None:
            if value not in external_lists:
                external_lists.append(value)
            continue
        if value not in missing_lists:
            missing_lists.append(value)
    if missing_lists:
        issues.append(
            PresetTxtImportIssue(
                "warning",
                "LIST_DEPENDENCIES_MISSING",
                "Preset импортируется как неполный, но runtime будет заблокирован до появления hostlist/ipset files: "
                + ", ".join(missing_lists),
            )
        )

    title = metadata.get("preset") or source.stem
    builtin_version = metadata.get("builtinversion", "")
    description = metadata.get("description", "")
    runtime_args = tuple(adapted)
    parsed = parse_preset_args(runtime_args, preset_id="txt-import-preview", title=title, source_path=str(source))
    if not parsed.profiles:
        issues.append(PresetTxtImportIssue("error", "NO_TRAFFIC_PROFILES", "После адаптации не осталось ни одного traffic-profile"))
    elif parsed.action_count == 0:
        issues.append(PresetTxtImportIssue("warning", "NO_LUA_DESYNC", "Traffic-профили не содержат --lua-desync actions"))

    return PresetTxtImportAnalysis(
        source_path=source,
        encoding=encoding,
        title=title.strip() or source.stem,
        builtin_version=builtin_version,
        description=description,
        source_sha256=sha256(raw).hexdigest(),
        source_args=source_args,
        runtime_args=runtime_args,
        parsed_preset=parsed,
        confidence=confidence,
        adaptations=tuple(adaptations),
        issues=tuple(issues),
        windows_tcp_capture_hint=tuple(tcp_hint),
        windows_udp_capture_hint=tuple(udp_hint),
        missing_list_dependencies=tuple(missing_lists),
        external_list_dependencies=tuple(external_lists),
    )


def import_txt_preset(
    path: Path | str,
    root: Path | None = None,
    dependency_root: Path | None = None,
) -> PresetTxtImportResult:
    layout = discover_layout(root)
    analysis = analyze_txt_preset(path, layout.root, dependency_root=dependency_root)
    if not analysis.can_import:
        details = "; ".join(item.message for item in analysis.errors) or "не прошла проверка структуры"
        raise ValueError(f"TXT preset не импортирован: {details}")

    realized_args, list_notes, unresolved_lists, asset_roots = _materialize_list_dependencies(
        analysis, layout.root, dependency_root
    )
    realized_adaptations = analysis.adaptations + list_notes
    realized_issues = tuple(item for item in analysis.issues if item.code != "LIST_DEPENDENCIES_MISSING")
    if unresolved_lists:
        realized_issues += (
            PresetTxtImportIssue(
                "warning",
                "LIST_DEPENDENCIES_MISSING",
                "Preset импортирован как неполный; runtime заблокирован до появления hostlist/ipset files: "
                + ", ".join(unresolved_lists),
            ),
        )
    analysis = replace(
        analysis,
        runtime_args=realized_args,
        parsed_preset=parse_preset_args(
            realized_args,
            preset_id="txt-import-realized",
            title=analysis.title,
            source_path=str(analysis.source_path),
        ),
        adaptations=realized_adaptations,
        issues=realized_issues,
        missing_list_dependencies=unresolved_lists,
        external_list_dependencies=(),
    )

    source_extra: dict[str, object] = {
        "engine": "nfqws2",
        "id": "txt-preset-import",
        "name": analysis.source_path.name,
        "importKind": "full-preset-txt",
        "sourceFilename": analysis.source_path.name,
        "sourceSha256": analysis.source_sha256,
        "detectionConfidence": analysis.confidence,
    }
    if analysis.builtin_version:
        source_extra["builtinVersion"] = analysis.builtin_version
    if analysis.description:
        source_extra["description"] = analysis.description
    if asset_roots:
        source_extra["listAssetsRoot"] = asset_roots[0]
    if analysis.missing_list_dependencies:
        source_extra["missingListDependencies"] = list(analysis.missing_list_dependencies)

    notes = [
        "Imported as a full ordered preset; no profile was selected or executed automatically.",
        *analysis.adaptations,
        *(f"Import warning {item.code}: {item.message}" for item in analysis.warnings),
    ]
    mutation = create_owner_preset_from_runtime_args(
        analysis.title,
        analysis.runtime_args,
        root=root,
        make_unique=True,
        action="txt-imported",
        source_preset_extra=source_extra,
        extra_notes=notes,
    )
    return PresetTxtImportResult(mutation=mutation, analysis=analysis)
