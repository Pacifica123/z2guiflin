"""Редактор owner-managed пресетов без запуска nfqws2.

Модуль меняет только файлы проекта: canonical preset ``.txt``, metadata JSON и
``strategies/catalog.json``. Firewall, systemd, NFQUEUE и runtime session здесь
не трогаются.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import tempfile
from typing import Iterable

from .presets import PresetCatalogEntry, load_preset, load_preset_catalog
from .workspace_profiles import load_active_strategy_selection, load_strategy_catalog, select_workspace_strategy
from ..models.preset import TrafficProfile, ZapretPreset, parse_preset_args
from ..models.service_targets import normalize_service_targets, service_target_host_token
from ..project_paths import discover_layout


PRESET_EDITOR_SCHEMA_VERSION = 1
PRESET_TARGET_NONE = "none"
PRESET_TARGET_DOMAINS = "domains"
PRESET_TARGET_HOSTLIST = "hostlist"
PRESET_TARGET_IPS = "ips"
PRESET_TARGET_IPSET = "ipset"
SUPPORTED_PRESET_TARGET_KINDS = (
    PRESET_TARGET_NONE,
    PRESET_TARGET_DOMAINS,
    PRESET_TARGET_HOSTLIST,
    PRESET_TARGET_IPS,
    PRESET_TARGET_IPSET,
)

PRESET_PROTOCOL_ANY = "any"
PRESET_PROTOCOL_TCP = "tcp"
PRESET_PROTOCOL_UDP = "udp"
SUPPORTED_PRESET_PROTOCOLS = (
    PRESET_PROTOCOL_ANY,
    PRESET_PROTOCOL_TCP,
    PRESET_PROTOCOL_UDP,
)

_DEFAULT_GLOBAL_ARGS = (
    "--lua-init=@core/zapret2/lua/zapret-lib.lua",
    "--lua-init=@core/zapret2/lua/zapret-antidpi.lua",
)

_FILTER_PREFIXES = (
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

_PROFILE_CONTROL_PREFIXES = (
    "--name=",
    "--skip",
    "--template",
    "--import=",
    "--cookie",
)

_FORBIDDEN_MANUAL_PREFIXES = (
    "--new",
    "--lua-init",
    "--blob",
    "--qnum",
    "--daemon",
    "--pidfile",
    "--user",
    "--uid",
    "--gid",
    *_FILTER_PREFIXES,
    "--name",
    "--skip",
    "--template",
    "--import",
)

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$")
_SAFE_PORTS_RE = re.compile(r"^[0-9*~,\-]+$")
_SAFE_L3_RE = re.compile(r"^[A-Za-z0-9_,\-]+$")
_SAFE_L7_RE = re.compile(r"^[A-Za-z0-9_,\-]+$")
_SAFE_IP_TOKEN_RE = re.compile(r"^[0-9A-Fa-f:.%/]+$")
_CYRILLIC_SLUG_MAP = str.maketrans(
    {
        "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
        "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
        "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
        "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
        "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    }
)


@dataclass(frozen=True)
class ProfileStrategyTemplate:
    template_id: str
    title: str
    source_preset_id: str
    source_profile_name: str
    strategy_args: tuple[str, ...]
    strategy_label: str
    range_label: str
    direction_label: str
    suggested_l7: tuple[str, ...] = ()

    def to_text(self) -> str:
        return "\n".join(
            [
                f"Strategy template: {self.title}",
                f"source preset: {self.source_preset_id}",
                f"source profile: {self.source_profile_name}",
                f"strategy: {self.strategy_label}",
                f"range: {self.range_label}",
                f"direction: {self.direction_label}",
                *(f"  {arg}" for arg in self.strategy_args),
            ]
        )


@dataclass(frozen=True)
class EditableTrafficProfile:
    name: str
    protocol: str
    ports: str = ""
    l3: str = ""
    l7: str = ""
    target_kind: str = PRESET_TARGET_NONE
    target_value: str = ""
    strategy_args: tuple[str, ...] = ()
    enabled: bool = True

    def validate(self) -> None:
        if not self.name.strip():
            raise ValueError("Имя профиля не может быть пустым")
        if "\n" in self.name or "\r" in self.name:
            raise ValueError("Имя профиля должно быть одной строкой")
        if self.protocol not in SUPPORTED_PRESET_PROTOCOLS:
            raise ValueError(f"Неподдерживаемый протокол профиля: {self.protocol}")
        if self.target_kind not in SUPPORTED_PRESET_TARGET_KINDS:
            raise ValueError(f"Неподдерживаемый тип цели: {self.target_kind}")
        if self.protocol in {PRESET_PROTOCOL_TCP, PRESET_PROTOCOL_UDP}:
            ports = self.ports.strip()
            if not ports:
                raise ValueError("Для TCP/UDP профиля нужно указать порт или диапазон")
            if not _SAFE_PORTS_RE.fullmatch(ports):
                raise ValueError(f"Недопустимое поле портов: {ports!r}")
        elif self.ports.strip():
            raise ValueError("Порты нельзя задавать при протоколе any")
        if self.l3.strip() and not _SAFE_L3_RE.fullmatch(self.l3.strip()):
            raise ValueError(f"Недопустимый filter-l3: {self.l3!r}")
        if self.l7.strip() and not _SAFE_L7_RE.fullmatch(self.l7.strip()):
            raise ValueError(f"Недопустимый filter-l7: {self.l7!r}")
        _validate_target(self.target_kind, self.target_value)
        validate_profile_strategy_args(self.strategy_args)
        if (
            self.protocol == PRESET_PROTOCOL_ANY
            and not self.l3.strip()
            and not self.l7.strip()
            and self.target_kind == PRESET_TARGET_NONE
        ):
            raise ValueError(
                "Профиль без protocol/L3/L7/target перехватит любой трафик. "
                "Добавьте хотя бы один явный filter."
            )

    def to_raw_args(self) -> tuple[str, ...]:
        self.validate()
        args: list[str] = [f"--name={self.name.strip()}"]
        if not self.enabled:
            args.append("--skip")
        if self.protocol == PRESET_PROTOCOL_TCP:
            args.append(f"--filter-tcp={self.ports.strip()}")
        elif self.protocol == PRESET_PROTOCOL_UDP:
            args.append(f"--filter-udp={self.ports.strip()}")
        if self.l3.strip():
            args.append(f"--filter-l3={self.l3.strip()}")
        if self.l7.strip():
            args.append(f"--filter-l7={self.l7.strip()}")
        args.extend(_target_args(self.target_kind, self.target_value))
        args.extend(self.strategy_args)
        return tuple(args)


@dataclass(frozen=True)
class PresetMutationResult:
    action: str
    preset_id: str
    title: str
    preset_path: Path
    metadata_path: Path
    profile_count: int
    selected_preset_id: str

    def to_text(self) -> str:
        return "\n".join(
            [
                f"Preset constructor: {self.action}",
                f"preset: {self.preset_id}",
                f"title: {self.title}",
                f"preset file: {self.preset_path}",
                f"metadata file: {self.metadata_path}",
                f"profiles: {self.profile_count}",
                f"currently selected preset: {self.selected_preset_id}",
                "executes nfqws2 now: no",
                "mutates firewall/services now: no",
                "invalidates previous prepared start-plan when runtime args changed: yes",
            ]
        )


@dataclass(frozen=True)
class PresetDeletionResult:
    preset_id: str
    title: str
    preset_path: Path
    metadata_path: Path
    selected_preset_id: str
    selection_fallback_applied: bool
    removed_asset_root: Path | None = None

    def to_text(self) -> str:
        lines = [
            "Preset constructor: preset-removed",
            f"preset: {self.preset_id}",
            f"title: {self.title}",
            f"removed preset file: {self.preset_path}",
            f"removed metadata file: {self.metadata_path}",
            f"currently selected preset: {self.selected_preset_id}",
            f"selection fallback applied: {'yes' if self.selection_fallback_applied else 'no'}",
            "executes nfqws2 now: no",
            "mutates firewall/services now: no",
        ]
        if self.removed_asset_root is not None:
            lines.append(f"removed unshared imported assets: {self.removed_asset_root}")
        return "\n".join(lines)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _slug(value: str) -> str:
    transliterated = value.lower().translate(_CYRILLIC_SLUG_MAP)
    slug = re.sub(r"[^a-z0-9]+", "-", transliterated).strip("-")
    slug = re.sub(r"-+", "-", slug)
    if len(slug) < 3:
        slug = f"preset-{slug or 'owner'}"
    return slug[:64].strip("-")


def _validate_preset_id(value: str) -> str:
    preset_id = value.strip().lower()
    if not _ID_RE.fullmatch(preset_id):
        raise ValueError(
            "ID пресета должен содержать 3–64 символа: a-z, 0-9 и дефис; "
            "начало и конец — буква или цифра"
        )
    return preset_id


def _split_csv_or_space(value: str) -> tuple[str, ...]:
    return tuple(item for item in re.split(r"[\s,]+", value.strip()) if item)


def _validate_target(kind: str, value: str) -> None:
    raw = value.strip()
    if kind == PRESET_TARGET_NONE:
        if raw:
            raise ValueError("Для target=none поле цели должно быть пустым")
        return
    if not raw:
        raise ValueError("Поле цели не может быть пустым")
    if kind == PRESET_TARGET_DOMAINS:
        normalize_service_targets(_split_csv_or_space(raw))
        return
    if kind in {PRESET_TARGET_HOSTLIST, PRESET_TARGET_IPSET}:
        if "\n" in raw or "\r" in raw or raw.startswith("/") or ".." in Path(raw).parts:
            raise ValueError("Путь списка должен быть относительным путём внутри проекта")
        if any(ch in raw for ch in (";", "|", "&", "`", "$", "<", ">")):
            raise ValueError("Путь списка содержит недопустимые shell-символы")
        return
    if kind == PRESET_TARGET_IPS:
        values = _split_csv_or_space(raw)
        if not values or any(not _SAFE_IP_TOKEN_RE.fullmatch(item) for item in values):
            raise ValueError("IP/CIDR цель содержит недопустимое значение")
        return
    raise ValueError(f"Неподдерживаемый тип цели: {kind}")


def _target_args(kind: str, value: str) -> tuple[str, ...]:
    _validate_target(kind, value)
    raw = value.strip()
    if kind == PRESET_TARGET_NONE:
        return ()
    if kind == PRESET_TARGET_DOMAINS:
        hosts = tuple(service_target_host_token(item) for item in normalize_service_targets(_split_csv_or_space(raw)))
        hosts = tuple(item for item in hosts if item)
        if not hosts:
            raise ValueError("Из domain targets не удалось получить host tokens")
        return ("--hostlist-domains=" + ",".join(dict.fromkeys(hosts)),)
    if kind == PRESET_TARGET_HOSTLIST:
        return (f"--hostlist={raw}",)
    if kind == PRESET_TARGET_IPS:
        return ("--ipset-ip=" + ",".join(_split_csv_or_space(raw)),)
    if kind == PRESET_TARGET_IPSET:
        return (f"--ipset={raw}",)
    raise ValueError(f"Неподдерживаемый тип цели: {kind}")


def parse_manual_strategy_text(text: str) -> tuple[str, ...]:
    args: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            tokens = shlex.split(line, posix=True)
        except ValueError as exc:
            raise ValueError(f"Не удалось разобрать строку стратегии: {line!r}: {exc}") from exc
        args.extend(tokens)
    result = tuple(args)
    validate_profile_strategy_args(result)
    return result


def strategy_args_to_text(args: Iterable[str]) -> str:
    return "\n".join(str(arg) for arg in args)


def validate_profile_strategy_args(args: Iterable[str]) -> tuple[str, ...]:
    normalized = tuple(str(arg).strip() for arg in args if str(arg).strip())
    if not normalized:
        raise ValueError("Стратегия профиля не может быть пустой")
    for arg in normalized:
        if not arg.startswith("--"):
            raise ValueError(f"Позиционный аргумент запрещён в стратегии профиля: {arg!r}")
        if arg == "--new" or any(arg.startswith(prefix) for prefix in _FORBIDDEN_MANUAL_PREFIXES):
            raise ValueError(
                f"Аргумент {arg!r} относится к preset/global/filter слою. "
                "В ручной стратегии оставьте payload/range/lua-desync и профильные action options."
            )
    if not any(arg.startswith("--lua-desync=") for arg in normalized):
        raise ValueError("Стратегия профиля должна содержать хотя бы один --lua-desync")
    return normalized


def profile_strategy_args(profile: TrafficProfile) -> tuple[str, ...]:
    result: list[str] = []
    for arg in profile.raw_args:
        if arg.startswith(_FILTER_PREFIXES):
            continue
        if arg == "--skip" or arg.startswith("--name="):
            continue
        # Template/import semantics are not copied blindly into a standalone
        # selector item: without the source template block they can change meaning.
        if arg.startswith(("--template", "--import=")):
            continue
        result.append(arg)
    return tuple(result)


_STANDARD_BLOCKCHECK_LUA_IMPORTS = {
    "--lua-init=@core/zapret2/lua/zapret-lib.lua",
    "--lua-init=@core/zapret2/lua/zapret-antidpi.lua",
}


def split_blockcheck_profile_args(args: Iterable[str]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Разделить blockcheck candidate на suggested filters и profile strategy.

    Два стандартных Lua import уже добавляются на уровне owner-managed preset и
    поэтому не копируются в профиль. Любые другие ``--lua-init`` или ``--blob``
    могут определять значения, на которые ссылается candidate. Молча удалить их
    означало бы изменить найденную стратегию, поэтому такой candidate отклоняется.
    """

    filter_args: list[str] = []
    strategy_args: list[str] = []
    unsupported_globals: list[str] = []
    for raw in args:
        arg = str(raw).strip()
        if not arg:
            continue
        if arg in _STANDARD_BLOCKCHECK_LUA_IMPORTS:
            continue
        if arg.startswith("--lua-init=") or arg.startswith("--blob="):
            unsupported_globals.append(arg)
            continue
        if arg.startswith(_FILTER_PREFIXES):
            filter_args.append(arg)
            continue
        if arg == "--new" or arg.startswith(("--name=", "--skip")):
            continue
        strategy_args.append(arg)
    if unsupported_globals:
        rendered = "\n".join(f"- {item}" for item in unsupported_globals)
        raise ValueError(
            "Blockcheck candidate содержит дополнительные global Lua/blob определения. "
            "Его нельзя безопасно вставить как один профиль без потери смысла:\n" + rendered
        )
    validate_profile_strategy_args(strategy_args)
    return tuple(filter_args), tuple(strategy_args)


def list_profile_strategy_templates(root: Path | None = None) -> tuple[ProfileStrategyTemplate, ...]:
    catalog = load_preset_catalog(root)
    templates: list[ProfileStrategyTemplate] = []
    seen: set[tuple[str, ...]] = set()
    for entry in catalog.entries:
        for profile in entry.preset.profiles:
            args = profile_strategy_args(profile)
            if not args or not any(arg.startswith("--lua-desync=") for arg in args):
                continue
            if args in seen:
                continue
            try:
                validate_profile_strategy_args(args)
            except ValueError:
                continue
            seen.add(args)
            template_id = f"{entry.preset.preset_id}:{profile.index + 1}"
            templates.append(
                ProfileStrategyTemplate(
                    template_id=template_id,
                    title=f"{profile.strategy_label} — {entry.preset.title} / {profile.name}",
                    source_preset_id=entry.preset.preset_id,
                    source_profile_name=profile.name,
                    strategy_args=args,
                    strategy_label=profile.strategy_label,
                    range_label=profile.range_label,
                    direction_label=profile.direction_label,
                    suggested_l7=profile.traffic_filter.l7,
                )
            )
    return tuple(templates)


def _metadata_is_editor_managed(entry: PresetCatalogEntry) -> bool:
    source = entry.metadata.source_preset or {}
    return bool(source.get("editorManaged")) and int(source.get("editorSchemaVersion", 0) or 0) == PRESET_EDITOR_SCHEMA_VERSION


def is_preset_editor_managed(preset_id: str, root: Path | None = None) -> bool:
    return _metadata_is_editor_managed(load_preset(preset_id, root))


def _catalog_path(root: Path) -> Path:
    return root / "strategies" / "catalog.json"


def _metadata_path_for(root: Path, preset_id: str) -> Path:
    return root / "strategies" / "workspace" / f"{preset_id}.json"


def _preset_path_for(root: Path, preset_id: str) -> Path:
    return root / "presets" / "workspace" / f"{preset_id}.txt"


def _relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _render_preset_file(preset_id: str, title: str, args: tuple[str, ...]) -> str:
    lines = [
        "# z2guiflin owner-managed Zapret2 preset",
        f"# id: {preset_id}",
        f"# title: {title}",
        "# Создан конструктором пресетов. Порядок profile-блоков важен: first match wins.",
        *args,
    ]
    return "\n".join(lines).rstrip() + "\n"


def _metadata_payload(
    *,
    preset_id: str,
    title: str,
    preset_rel: str,
    runtime_args: tuple[str, ...],
    created_at: str,
    updated_at: str,
    source_preset_extra: dict[str, object] | None = None,
    extra_notes: Iterable[str] = (),
) -> dict[str, object]:
    parsed = parse_preset_args(runtime_args, preset_id=preset_id, title=title, source_path=preset_rel)
    domain_targets: list[str] = []
    for profile in parsed.profiles:
        for host in profile.traffic_filter.hostlist_domains:
            if host not in domain_targets:
                domain_targets.append(host)
    source_preset: dict[str, object] = {
        "engine": "nfqws2",
        "id": "preset-constructor",
        "name": "z2guiflin owner preset constructor",
        "editorManaged": True,
        "editorSchemaVersion": PRESET_EDITOR_SCHEMA_VERSION,
        "createdAt": created_at,
        "updatedAt": updated_at,
    }
    if source_preset_extra:
        source_preset.update(source_preset_extra)
    # Импорт никогда не должен случайно снять owner-managed маркер: именно он
    # разрешает дальнейшее редактирование через конструктор.
    source_preset["editorManaged"] = True
    source_preset["editorSchemaVersion"] = PRESET_EDITOR_SCHEMA_VERSION
    source_preset["createdAt"] = created_at
    source_preset["updatedAt"] = updated_at

    notes = [
        "Editing changes only project files and never applies runtime/firewall automatically.",
        "Changing profile order changes first-match priority.",
        "A previous prepared start-plan becomes stale after runtimeArgs change.",
    ]
    notes.extend(str(item).strip() for item in extra_notes if str(item).strip())

    return {
        "schemaVersion": 1,
        "id": preset_id,
        "title": title,
        "summary": f"Owner-managed preset: {len(parsed.profiles)} traffic profiles.",
        "philosophy": "preset-constructor-owner-managed",
        "intendedFor": [
            "manual composition of ordered Zapret2 traffic profiles",
            "owner review before selection and Default workflow start",
        ],
        "workflow": ["construct", "review-order", "select-preset", "plan", "owner-confirms", "execute-later"],
        "capabilities": {
            "readsProfiles": True,
            "readsHostlists": True,
            "usesLocalBuildPlan": True,
            "executesAutomatically": False,
            "requiresSudoAtStage7": False,
            "mutatesServicesOrFirewallAtStage7": False,
        },
        "runtimeArgs": list(runtime_args),
        "presetPath": preset_rel,
        "serviceTarget": {
            "presetId": "custom",
            "title": "Owner preset constructor",
            "summary": "Targets are defined independently in ordered traffic profiles.",
            "nonVoice": False,
            "targets": domain_targets,
        },
        "sourcePreset": source_preset,
        "notes": notes,
    }


def _atomic_multi_write(payloads: dict[Path, str]) -> None:
    backups: dict[Path, bytes | None] = {}
    temp_paths: dict[Path, Path] = {}
    try:
        for path, text in payloads.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            backups[path] = path.read_bytes() if path.exists() else None
            fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
            temp_path = Path(temp_name)
            temp_paths[path] = temp_path
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
        for path, temp_path in temp_paths.items():
            os.replace(temp_path, path)
    except Exception:
        for path, old in backups.items():
            try:
                if old is None:
                    path.unlink(missing_ok=True)
                else:
                    path.write_bytes(old)
            except Exception:
                pass
        raise
    finally:
        for temp_path in temp_paths.values():
            temp_path.unlink(missing_ok=True)


def _catalog_with_path(root: Path, metadata_path: Path) -> str:
    catalog_path = _catalog_path(root)
    data = json.loads(catalog_path.read_text(encoding="utf-8"))
    files = [str(item) for item in data.get("strategyFiles", [])]
    rel = _relative(metadata_path, root)
    if rel not in files:
        files.append(rel)
    data["strategyFiles"] = files
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _catalog_without_path(root: Path, metadata_path: Path) -> str:
    catalog_path = _catalog_path(root)
    data = json.loads(catalog_path.read_text(encoding="utf-8"))
    rel = _relative(metadata_path, root)
    files = [str(item) for item in data.get("strategyFiles", []) if str(item) != rel]
    if len(files) == len(data.get("strategyFiles", [])):
        raise ValueError(f"Preset metadata отсутствует в strategy catalog: {rel}")
    if str(data.get("defaultStrategyId", "")) == metadata_path.stem:
        raise ValueError("Catalog default preset удалять нельзя")
    data["strategyFiles"] = files
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _safe_imported_asset_root(root: Path, value: object) -> Path | None:
    raw = str(value or "").strip().replace("\\", "/")
    if not raw:
        return None
    rel = Path(raw)
    if rel.is_absolute() or ".." in rel.parts:
        return None
    allowed = root / "presets" / "imported-assets"
    candidate = (root / rel).resolve()
    try:
        candidate.relative_to(allowed.resolve())
    except ValueError:
        return None
    return candidate


def _asset_root_is_shared(root: Path, asset_root: Path, excluding_preset_id: str) -> bool:
    target = asset_root.resolve()
    for other in load_preset_catalog(root).entries:
        if other.preset.preset_id == excluding_preset_id:
            continue
        source = other.metadata.source_preset or {}
        candidate = _safe_imported_asset_root(root, source.get("listAssetsRoot"))
        if candidate is not None and candidate.resolve() == target:
            return True
    return False


def _assert_mutation_allowed(root: Path, preset_id: str) -> None:
    """Не менять выбранный preset под живым nfqws2 процессом."""

    try:
        from .runtime_session import runtime_session_status

        status = runtime_session_status(root, "default")
    except Exception:
        return
    if status.state != "running":
        return
    catalog = load_preset_catalog(root)
    if catalog.selected_preset_id == preset_id:
        raise ValueError(
            "Выбранный пресет сейчас запущен. Сначала остановите Default workflow, "
            "затем изменяйте его profiles/order."
        )


def _entry_created_at(entry: PresetCatalogEntry) -> str:
    source = entry.metadata.source_preset or {}
    return str(source.get("createdAt") or _utc_now())


def _write_existing_preset(root: Path, entry: PresetCatalogEntry, preset: ZapretPreset, action: str) -> PresetMutationResult:
    if not _metadata_is_editor_managed(entry):
        raise ValueError(
            f"Пресет {entry.preset.preset_id} не создан конструктором. "
            "Чтобы не менять reference/community файлы скрыто, создайте новый пресет и копируйте profiles в него."
        )
    _assert_mutation_allowed(root, preset.preset_id)
    preset_path = root / entry.metadata.preset_path
    metadata_path = _metadata_path_for(root, preset.preset_id)
    runtime_args = preset.to_runtime_args()
    created_at = _entry_created_at(entry)
    now = _utc_now()
    metadata = _metadata_payload(
        preset_id=preset.preset_id,
        title=preset.title,
        preset_rel=_relative(preset_path, root),
        runtime_args=runtime_args,
        created_at=created_at,
        updated_at=now,
    )
    payloads = {
        preset_path: _render_preset_file(preset.preset_id, preset.title, runtime_args),
        metadata_path: json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    }
    # Metadata path should already be in catalog, but adding it is idempotent and
    # also repairs an interrupted early constructor version.
    payloads[_catalog_path(root)] = _catalog_with_path(root, metadata_path)
    _atomic_multi_write(payloads)
    refreshed = load_preset(preset.preset_id, root)
    selected = load_preset_catalog(root).selected_preset_id
    return PresetMutationResult(
        action=action,
        preset_id=preset.preset_id,
        title=refreshed.preset.title,
        preset_path=preset_path,
        metadata_path=metadata_path,
        profile_count=len(refreshed.preset.profiles),
        selected_preset_id=selected,
    )


def create_owner_preset_from_runtime_args(
    title: str,
    runtime_args: Iterable[str],
    root: Path | None = None,
    *,
    preset_id: str = "",
    make_unique: bool = False,
    action: str = "created",
    source_preset_extra: dict[str, object] | None = None,
    extra_notes: Iterable[str] = (),
) -> PresetMutationResult:
    """Создать редактируемый owner preset из уже подготовленного полного argv.

    Функция предназначена в том числе для безопасных import adapters. Она не
    нормализует и не переставляет argv: после записи действует тот же round-trip
    контракт, что и для остальных canonical preset-файлов.
    """

    layout = discover_layout(root)
    clean_title = title.strip()
    if not clean_title:
        raise ValueError("Название пресета не может быть пустым")
    base_candidate = _validate_preset_id(preset_id or _slug(clean_title))
    existing = load_strategy_catalog(layout.root).by_id()
    candidate = base_candidate
    if make_unique:
        suffix = 2
        while candidate in existing or _preset_path_for(layout.root, candidate).exists() or _metadata_path_for(layout.root, candidate).exists():
            tail = f"-{suffix}"
            candidate = f"{base_candidate[:63-len(tail)].rstrip('-')}{tail}"
            candidate = _validate_preset_id(candidate)
            suffix += 1
    elif candidate in existing:
        raise ValueError(f"Пресет с ID {candidate!r} уже существует")

    normalized = tuple(str(arg).strip() for arg in runtime_args if str(arg).strip())
    if not normalized:
        raise ValueError("Полный пресет не может быть пустым")
    parsed = parse_preset_args(normalized, preset_id=candidate, title=clean_title)
    if parsed.to_runtime_args() != normalized:
        raise ValueError("Внутренняя ошибка: полный preset argv не прошёл round-trip")

    preset_path = _preset_path_for(layout.root, candidate)
    metadata_path = _metadata_path_for(layout.root, candidate)
    if preset_path.exists() or metadata_path.exists():
        raise ValueError(f"Файлы нового пресета уже существуют: {candidate}")
    now = _utc_now()
    preset_rel = _relative(preset_path, layout.root)
    metadata = _metadata_payload(
        preset_id=candidate,
        title=clean_title,
        preset_rel=preset_rel,
        runtime_args=normalized,
        created_at=now,
        updated_at=now,
        source_preset_extra=source_preset_extra,
        extra_notes=extra_notes,
    )
    payloads = {
        preset_path: _render_preset_file(candidate, clean_title, normalized),
        metadata_path: json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        _catalog_path(layout.root): _catalog_with_path(layout.root, metadata_path),
    }
    _atomic_multi_write(payloads)
    refreshed = load_preset(candidate, layout.root)
    selected = load_preset_catalog(layout.root).selected_preset_id
    return PresetMutationResult(
        action=action,
        preset_id=candidate,
        title=clean_title,
        preset_path=preset_path,
        metadata_path=metadata_path,
        profile_count=len(refreshed.preset.profiles),
        selected_preset_id=selected,
    )


def create_owner_preset(
    title: str,
    root: Path | None = None,
    *,
    preset_id: str = "",
    global_args: Iterable[str] = _DEFAULT_GLOBAL_ARGS,
) -> PresetMutationResult:
    layout = discover_layout(root)
    clean_title = title.strip()
    if not clean_title:
        raise ValueError("Название пресета не может быть пустым")
    candidate = _validate_preset_id(preset_id or _slug(clean_title))
    existing = load_strategy_catalog(layout.root).by_id()
    if candidate in existing:
        raise ValueError(f"Пресет с ID {candidate!r} уже существует")
    normalized_globals = tuple(str(arg).strip() for arg in global_args if str(arg).strip())
    if not normalized_globals:
        raise ValueError("Новый пресет должен содержать global lua-init args")
    if any(arg.startswith(_FILTER_PREFIXES) or arg.startswith(("--new", "--name", "--lua-desync")) for arg in normalized_globals):
        raise ValueError("global_args содержат profile/filter/action аргументы")

    preset_path = _preset_path_for(layout.root, candidate)
    metadata_path = _metadata_path_for(layout.root, candidate)
    if preset_path.exists() or metadata_path.exists():
        raise ValueError(f"Файлы нового пресета уже существуют: {candidate}")
    now = _utc_now()
    preset_rel = _relative(preset_path, layout.root)
    metadata = _metadata_payload(
        preset_id=candidate,
        title=clean_title,
        preset_rel=preset_rel,
        runtime_args=normalized_globals,
        created_at=now,
        updated_at=now,
    )
    payloads = {
        preset_path: _render_preset_file(candidate, clean_title, normalized_globals),
        metadata_path: json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        _catalog_path(layout.root): _catalog_with_path(layout.root, metadata_path),
    }
    _atomic_multi_write(payloads)
    # Full catalog load is the post-write contract: presetPath/runtimeArgs must
    # match exactly and the new metadata must remain plan-only.
    load_preset(candidate, layout.root)
    selected = load_preset_catalog(layout.root).selected_preset_id
    return PresetMutationResult(
        action="created",
        preset_id=candidate,
        title=clean_title,
        preset_path=preset_path,
        metadata_path=metadata_path,
        profile_count=0,
        selected_preset_id=selected,
    )


def remove_owner_preset(preset_id: str, root: Path | None = None) -> PresetDeletionResult:
    """Удалить owner-managed preset и его metadata без runtime side effects."""

    layout = discover_layout(root)
    entry = load_preset(preset_id, layout.root)
    if not _metadata_is_editor_managed(entry):
        raise ValueError(
            f"Пресет {preset_id} не создан конструктором. Reference/community preset удалять через GUI нельзя."
        )
    _assert_mutation_allowed(layout.root, preset_id)

    strategy_catalog = load_strategy_catalog(layout.root)
    if preset_id == strategy_catalog.default_strategy_id:
        raise ValueError("Catalog default preset удалять нельзя")

    preset_path = (layout.root / entry.metadata.preset_path).resolve()
    metadata_path = _metadata_path_for(layout.root, preset_id).resolve()
    expected_preset = _preset_path_for(layout.root, preset_id).resolve()
    expected_metadata = _metadata_path_for(layout.root, preset_id).resolve()
    if preset_path != expected_preset or metadata_path != expected_metadata:
        raise ValueError("Owner preset имеет неожиданное расположение файлов; удаление заблокировано")

    selection = load_active_strategy_selection(layout.root, "default")
    selected_before = load_preset_catalog(layout.root).selected_preset_id
    fallback_applied = selected_before == preset_id or (selection is not None and selection.strategy_id == preset_id)
    fallback_id = strategy_catalog.default_strategy_id
    if fallback_applied:
        select_workspace_strategy(
            layout.root,
            strategy_id=fallback_id,
            profile_id="default",
            reason="preset-deleted-fallback",
        )

    source = entry.metadata.source_preset or {}
    asset_root = _safe_imported_asset_root(layout.root, source.get("listAssetsRoot"))
    shared_assets = asset_root is not None and _asset_root_is_shared(layout.root, asset_root, preset_id)

    # Сначала убрать запись из каталога: даже при неожиданной ошибке unlink
    # orphan files безопаснее, чем каталог, указывающий на частично удалённый preset.
    _atomic_multi_write({_catalog_path(layout.root): _catalog_without_path(layout.root, metadata_path)})
    preset_path.unlink(missing_ok=True)
    metadata_path.unlink(missing_ok=True)

    removed_asset_root: Path | None = None
    if asset_root is not None and not shared_assets and asset_root.is_dir():
        shutil.rmtree(asset_root)
        removed_asset_root = asset_root

    selected_after = load_preset_catalog(layout.root).selected_preset_id
    return PresetDeletionResult(
        preset_id=preset_id,
        title=entry.preset.title,
        preset_path=preset_path,
        metadata_path=metadata_path,
        selected_preset_id=selected_after,
        selection_fallback_applied=fallback_applied,
        removed_asset_root=removed_asset_root,
    )


def _replace_profiles(preset: ZapretPreset, raw_profiles: tuple[tuple[str, ...], ...]) -> ZapretPreset:
    args: list[str] = list(preset.global_args)
    for index, raw_args in enumerate(raw_profiles):
        if index:
            args.append("--new")
        args.extend(raw_args)
    return parse_preset_args(
        args,
        preset_id=preset.preset_id,
        title=preset.title,
        engine=preset.engine,
        source_path=preset.source_path,
    )


def add_owner_preset_profile(
    preset_id: str,
    profile: EditableTrafficProfile,
    root: Path | None = None,
    *,
    index: int | None = None,
) -> PresetMutationResult:
    layout = discover_layout(root)
    entry = load_preset(preset_id, layout.root)
    profile_args = profile.to_raw_args()
    rows = [item.raw_args for item in entry.preset.profiles]
    insert_at = len(rows) if index is None else int(index)
    if not 0 <= insert_at <= len(rows):
        raise ValueError(f"Позиция нового профиля вне диапазона: {insert_at}")
    rows.insert(insert_at, profile_args)
    updated = _replace_profiles(entry.preset, tuple(rows))
    return _write_existing_preset(layout.root, entry, updated, "profile-added")


def update_owner_preset_profile(
    preset_id: str,
    profile_index: int,
    profile: EditableTrafficProfile,
    root: Path | None = None,
) -> PresetMutationResult:
    layout = discover_layout(root)
    entry = load_preset(preset_id, layout.root)
    rows = [item.raw_args for item in entry.preset.profiles]
    if not 0 <= profile_index < len(rows):
        raise ValueError(f"Профиль #{profile_index + 1} не найден")
    rows[profile_index] = profile.to_raw_args()
    updated = _replace_profiles(entry.preset, tuple(rows))
    return _write_existing_preset(layout.root, entry, updated, "profile-updated")


def remove_owner_preset_profile(
    preset_id: str,
    profile_index: int,
    root: Path | None = None,
) -> PresetMutationResult:
    layout = discover_layout(root)
    entry = load_preset(preset_id, layout.root)
    rows = [item.raw_args for item in entry.preset.profiles]
    if not 0 <= profile_index < len(rows):
        raise ValueError(f"Профиль #{profile_index + 1} не найден")
    rows.pop(profile_index)
    updated = _replace_profiles(entry.preset, tuple(rows))
    return _write_existing_preset(layout.root, entry, updated, "profile-removed")


def move_owner_preset_profile(
    preset_id: str,
    profile_index: int,
    new_index: int,
    root: Path | None = None,
) -> PresetMutationResult:
    layout = discover_layout(root)
    entry = load_preset(preset_id, layout.root)
    rows = [item.raw_args for item in entry.preset.profiles]
    if not 0 <= profile_index < len(rows):
        raise ValueError(f"Профиль #{profile_index + 1} не найден")
    if not 0 <= new_index < len(rows):
        raise ValueError(f"Новая позиция #{new_index + 1} вне диапазона")
    row = rows.pop(profile_index)
    rows.insert(new_index, row)
    updated = _replace_profiles(entry.preset, tuple(rows))
    return _write_existing_preset(layout.root, entry, updated, "profile-moved")


def editable_profile_from_runtime(profile: TrafficProfile) -> EditableTrafficProfile:
    protocol = PRESET_PROTOCOL_ANY
    ports = ""
    if profile.traffic_filter.tcp:
        protocol = PRESET_PROTOCOL_TCP
        ports = ",".join(profile.traffic_filter.tcp)
    elif profile.traffic_filter.udp:
        protocol = PRESET_PROTOCOL_UDP
        ports = ",".join(profile.traffic_filter.udp)

    target_kind = PRESET_TARGET_NONE
    target_value = ""
    if profile.traffic_filter.hostlist_domains:
        target_kind = PRESET_TARGET_DOMAINS
        target_value = " ".join(profile.traffic_filter.hostlist_domains)
    elif profile.traffic_filter.hostlists:
        target_kind = PRESET_TARGET_HOSTLIST
        target_value = profile.traffic_filter.hostlists[0]
    elif profile.traffic_filter.inline_ips:
        target_kind = PRESET_TARGET_IPS
        target_value = " ".join(profile.traffic_filter.inline_ips)
    elif profile.traffic_filter.ipsets:
        target_kind = PRESET_TARGET_IPSET
        target_value = profile.traffic_filter.ipsets[0]

    return EditableTrafficProfile(
        name=profile.name,
        protocol=protocol,
        ports=ports,
        l3=",".join(profile.traffic_filter.l3),
        l7=",".join(profile.traffic_filter.l7),
        target_kind=target_kind,
        target_value=target_value,
        strategy_args=profile_strategy_args(profile),
        enabled=profile.enabled,
    )
