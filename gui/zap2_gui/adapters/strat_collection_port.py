"""Conservative strat_collection -> Zapret2 porting for entries with known mappings.

The adapter only emits nfqws2 args when every legacy option used by the entry is
covered by an explicit mapping. Unsupported entries remain reference-only.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Iterable

from .preset_editor import PresetMutationResult, create_owner_preset_from_runtime_args
from .presets import load_preset_catalog
from .strat_collection import StratCollectionEntry, load_strat_collection
from ..models.preset import parse_preset_args
from ..project_paths import discover_layout

_IGNORED_CAPTURE_PREFIXES = ("--wf-tcp", "--wf-udp", "--wf-l3")
_DIRECT_FILTER_PREFIXES = (
    "--filter-tcp=", "--filter-udp=", "--filter-l3=", "--filter-l7=",
    "--hostlist-domains=", "--hostlist-exclude-domains=", "--ipset-ip=", "--ipset-exclude-ip=",
)
_FILE_FILTER_PREFIXES = ("--hostlist=", "--hostlist-exclude=", "--ipset=", "--ipset-exclude=")
_UNSUPPORTED_PREFIXES = ("--dup", "--wssize")
_UNSUPPORTED_MODES = {"split", "split2", "disorder", "disorder2", "ipfrag1", "ipfrag2"}
_DIRECT_MODES = {
    "fake": "fake",
    "syndata": "syndata",
    "multisplit": "multisplit",
    "multidisorder": "multidisorder_legacy",
    "fakedsplit": "fakedsplit",
    "fakeddisorder": "fakeddisorder",
    "udplen": "udplen",
    "tamper": "dht_dn",
}
_FOOLING = {"badseq": "tcp_seq=-10000", "md5sig": "tcp_md5", "datanoack": "tcp_flags_unset=ack"}
_BLOB_OPTIONS = {
    "--dpi-desync-fake-tls": "tls",
    "--dpi-desync-fake-http": "http",
    "--dpi-desync-fake-quic": "quic",
    "--dpi-desync-fake-syndata": "syndata",
    "--dpi-desync-fakedsplit-pattern": "fakedsplit-pattern",
    "--dpi-desync-split-seqovl-pattern": "seqovl-pattern",
    "--dpi-desync-udplen-pattern": "udplen-pattern",
    "--dpi-desync-fake-unknown-udp": "unknown-udp",
}
_SAFE_NAME = re.compile(r"[^a-zA-Z0-9_]+")


@dataclass(frozen=True)
class StratPortPlan:
    entry_id: str
    title: str
    runtime_args: tuple[str, ...]
    unsupported: tuple[str, ...]
    adaptations: tuple[str, ...]

    @property
    def can_port(self) -> bool:
        return bool(self.runtime_args) and not self.unsupported

    def to_text(self) -> str:
        lines = [
            f"strat_collection port: {self.entry_id}",
            f"can port: {'yes' if self.can_port else 'no'}",
            f"runtime args: {len(self.runtime_args)}",
        ]
        if self.unsupported:
            lines.append("unsupported:")
            lines.extend(f"  - {item}" for item in self.unsupported)
        if self.adaptations:
            lines.append("adaptations:")
            lines.extend(f"  - {item}" for item in self.adaptations)
        return "\n".join(lines)


def _strip_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def _split_profiles(args: Iterable[str]) -> tuple[tuple[str, ...], ...]:
    result: list[list[str]] = [[]]
    for arg in args:
        if arg == "--new":
            if result[-1]:
                result.append([])
            continue
        if arg == "---]":
            continue
        result[-1].append(arg)
    return tuple(tuple(row) for row in result if row)


def _option_map(profile: tuple[str, ...]) -> dict[str, str]:
    result: dict[str, str] = {}
    for arg in profile:
        key, sep, value = arg.partition("=")
        if sep:
            result[key] = _strip_quotes(value)
        elif arg.startswith("--"):
            result[arg] = ""
    return result


def _project_asset_arg(collection_root: Path, project_root: Path, option: str, raw_value: str) -> str:
    value = _strip_quotes(raw_value).replace("\\", "/")
    source = (collection_root / value).resolve()
    source.relative_to(collection_root.resolve())
    if not source.is_file():
        raise ValueError(f"strat_collection asset отсутствует: {value}")
    return f"{option}={source.relative_to(project_root).as_posix()}"


def _blob_name(kind: str, value: str) -> str:
    stem = Path(value).stem
    return "strat_" + _SAFE_NAME.sub("_", f"{kind}_{stem}").strip("_").lower()


def _blob_definition(collection_root: Path, project_root: Path, kind: str, value: str) -> tuple[str, str]:
    clean = _strip_quotes(value).replace("\\", "/")
    source = (collection_root / clean).resolve()
    source.relative_to(collection_root.resolve())
    if not source.is_file():
        raise ValueError(f"strat_collection blob отсутствует: {clean}")
    name = _blob_name(kind, clean)
    return name, f"--blob={name}:@{source.relative_to(project_root).as_posix()}"


def _shared_fooling(options: dict[str, str], unsupported: list[str]) -> list[str]:
    result: list[str] = []
    fooling = options.get("--dpi-desync-fooling", "")
    for item in (part.strip() for part in fooling.split(",") if part.strip()):
        mapped = _FOOLING.get(item)
        if mapped:
            result.append(mapped)
        else:
            unsupported.append(f"--dpi-desync-fooling={item}")
    ttl = options.get("--dpi-desync-ttl")
    if ttl:
        result.extend((f"ip_ttl={ttl}", f"ip6_ttl={ttl}"))
    if "--dpi-desync-autottl" in options:
        raw = options.get("--dpi-desync-autottl", "") or "2"
        if re.fullmatch(r"-?\d+", raw):
            delta = raw if raw.startswith("-") else f"-{raw}"
            result.extend((f"ip_autottl={delta},3-20", f"ip6_autottl={delta},3-20"))
        else:
            unsupported.append(f"--dpi-desync-autottl={raw}")
    return result


def _profile_l7(profile: tuple[str, ...]) -> tuple[str, ...]:
    raw = next((arg.partition("=")[2] for arg in profile if arg.startswith("--filter-l7=")), "")
    return tuple(part.strip() for part in raw.split(",") if part.strip())


def _inferred_profile_guards(profile: tuple[str, ...]) -> tuple[str, ...]:
    l7 = _profile_l7(profile)
    if l7:
        payloads: list[str] = []
        mapping = {
            "http": ("http_req",),
            "tls": ("tls_client_hello",),
            "quic": ("quic_initial",),
            "discord": ("discord_ip_discovery",),
            "stun": ("stun",),
            "wireguard": ("wireguard_initiation", "wireguard_cookie"),
        }
        if all(item in mapping for item in l7):
            for item in l7:
                payloads.extend(mapping[item])
            return ("--payload=" + ",".join(dict.fromkeys(payloads)),)
        return ()
    tcp = next((arg.partition("=")[2] for arg in profile if arg.startswith("--filter-tcp=")), "")
    udp = next((arg.partition("=")[2] for arg in profile if arg.startswith("--filter-udp=")), "")
    tcp_parts = {part.strip() for part in tcp.split(",") if part.strip()}
    udp_parts = {part.strip() for part in udp.split(",") if part.strip()}
    if tcp_parts == {"80"}:
        return ("--filter-l7=http", "--payload=http_req")
    if tcp_parts == {"443"}:
        return ("--filter-l7=tls", "--payload=tls_client_hello")
    if udp_parts == {"443"}:
        return ("--filter-l7=quic", "--payload=quic_initial")
    return ()


def _choose_fake_blob(options: dict[str, str], profile: tuple[str, ...], blobs: dict[str, str], unsupported: list[str]) -> str | None:
    l7 = set(_profile_l7(profile))
    udp = next((arg.partition("=")[2] for arg in profile if arg.startswith("--filter-udp=")), "")
    tcp = next((arg.partition("=")[2] for arg in profile if arg.startswith("--filter-tcp=")), "")
    tcp_parts = {part.strip() for part in tcp.split(",") if part.strip()}
    udp_parts = {part.strip() for part in udp.split(",") if part.strip()}

    if "unknown-udp" in blobs and udp:
        return blobs["unknown-udp"]
    if "quic" in blobs and ("quic" in l7 or udp_parts == {"443"}):
        return blobs["quic"]
    if "http" in blobs and ("http" in l7 or tcp_parts == {"80"}):
        return blobs["http"]
    if "tls" in blobs and ("tls" in l7 or tcp_parts == {"443"}):
        return blobs["tls"]
    if "syndata" in blobs:
        return blobs["syndata"]

    if "http" in l7 or tcp_parts == {"80"}:
        return "fake_default_http"
    if "tls" in l7 or tcp_parts == {"443"}:
        return "fake_default_tls"
    if "quic" in l7 or udp_parts == {"443"}:
        return "fake_default_quic"
    if l7 and l7.issubset({"discord", "stun", "wireguard"}):
        # Exact payload form used by the bundled Zapret2 porting guide.
        return "0x00000000000000000000000000000000"

    unsupported.append("fake: для этого протокола нет однозначного payload/blob mapping")
    return None


def analyze_strat_port(entry: StratCollectionEntry, root: Path | None = None) -> StratPortPlan:
    layout = discover_layout(root)
    unsupported: list[str] = []
    adaptations: list[str] = []
    globals_out = [
        "--lua-init=@core/zapret2/lua/zapret-lib.lua",
        "--lua-init=@core/zapret2/lua/zapret-antidpi.lua",
    ]
    blob_defs: dict[str, str] = {}
    profiles_out: list[list[str]] = []

    for profile in _split_profiles(entry.winws_args):
        options = _option_map(profile)
        out: list[str] = []
        for arg in profile:
            key = arg.partition("=")[0]
            if arg.startswith(_IGNORED_CAPTURE_PREFIXES):
                adaptations.append(f"удалён Windows capture hint: {arg}")
                continue
            if arg.startswith(_DIRECT_FILTER_PREFIXES):
                out.append(arg.replace('"', ""))
                continue
            if arg.startswith(_FILE_FILTER_PREFIXES):
                try:
                    out.append(_project_asset_arg(entry.source_path.parent, layout.root, key, arg.partition("=")[2]))
                except Exception as exc:
                    unsupported.append(str(exc))
                continue
            if arg.startswith(_UNSUPPORTED_PREFIXES):
                unsupported.append(arg)
                continue
            if key == "--ipcache-hostname":
                if arg not in globals_out:
                    globals_out.append(arg)
                continue
            if key in _BLOB_OPTIONS or key.startswith("--dpi-desync"):
                continue
            if arg == "---]":
                continue
            unsupported.append(arg)

        for guard in _inferred_profile_guards(profile):
            if guard not in out:
                out.append(guard)

        mode_text = options.get("--dpi-desync", "")
        modes = tuple(part.strip() for part in mode_text.split(",") if part.strip())
        if not modes:
            unsupported.append("профиль без --dpi-desync")
            profiles_out.append(out)
            continue
        bad_modes = [mode for mode in modes if mode in _UNSUPPORTED_MODES or mode not in _DIRECT_MODES]
        if bad_modes:
            unsupported.extend(f"--dpi-desync={mode}" for mode in bad_modes)
            profiles_out.append(out)
            continue

        blobs: dict[str, str] = {}
        for option, kind in _BLOB_OPTIONS.items():
            if option not in options:
                continue
            try:
                name, definition = _blob_definition(entry.source_path.parent, layout.root, kind, options[option])
                blobs[kind] = name
                blob_defs.setdefault(name, definition)
            except Exception as exc:
                unsupported.append(str(exc))

        shared = _shared_fooling(options, unsupported)
        repeats = options.get("--dpi-desync-repeats")
        any_protocol = "--dpi-desync-any-protocol" in options
        split_pos = options.get("--dpi-desync-split-pos", "")
        split_tls = options.get("--dpi-desync-split-tls", "")
        seqovl = options.get("--dpi-desync-split-seqovl", "")
        tls_mod = options.get("--dpi-desync-fake-tls-mod", "")
        cutoff = options.get("--dpi-desync-cutoff", "")
        if cutoff:
            out.append(f"--out-range=-{cutoff}")

        for mode in modes:
            function = _DIRECT_MODES[mode]
            args: list[str] = []
            if function not in {"udplen", "dht_dn", "multidisorder_legacy"}:
                args.extend(shared)
                if repeats:
                    args.append(f"repeats={repeats}")
            if any_protocol and function != "dht_dn":
                args.append("payload=all")
            if function in {"multisplit", "multidisorder_legacy", "fakedsplit", "fakeddisorder"}:
                pos = split_pos or split_tls
                if pos:
                    args.append(f"pos={pos}")
                if seqovl:
                    args.append(f"seqovl={seqovl}")
                if "seqovl-pattern" in blobs:
                    args.append(f"seqovl_pattern={blobs['seqovl-pattern']}")
            if function in {"fake", "syndata"}:
                if function == "syndata" and "syndata" in blobs:
                    blob = blobs["syndata"]
                else:
                    blob = _choose_fake_blob(options, profile, blobs, unsupported)
                if blob:
                    args.append(f"blob={blob}")
                if tls_mod and (blob == blobs.get("tls") or blob == blobs.get("syndata") or (blob and "tls" in blob)):
                    args.append(f"tls_mod={tls_mod}")
            if function in {"fakedsplit", "fakeddisorder"} and "fakedsplit-pattern" in blobs:
                args.append(f"pattern={blobs['fakedsplit-pattern']}")
            if function == "udplen":
                increment = options.get("--dpi-desync-udplen-increment", "")
                if increment:
                    args.append(f"increment={increment}")
                if "udplen-pattern" in blobs:
                    args.append(f"pattern={blobs['udplen-pattern']}")
            out.append("--lua-desync=" + function + (":" + ":".join(args) if args else ""))
        profiles_out.append(out)

    runtime: list[str] = globals_out + list(blob_defs.values())
    for index, profile in enumerate(profiles_out):
        if index:
            runtime.append("--new")
        runtime.extend(profile)

    # Final parser round-trip is part of the safety boundary.
    if not unsupported:
        try:
            parsed = parse_preset_args(tuple(runtime), preset_id="strat-port-preview", title=entry.name)
            if not parsed.profiles or parsed.action_count == 0 or parsed.to_runtime_args() != tuple(runtime):
                unsupported.append("сгенерированный Zapret2 preset не прошёл parser round-trip")
        except Exception as exc:
            unsupported.append(f"Zapret2 parser: {exc}")

    return StratPortPlan(entry.entry_id, f"strat_collection: {entry.name}", tuple(runtime) if not unsupported else (), tuple(dict.fromkeys(unsupported)), tuple(dict.fromkeys(adaptations)))


def find_existing_strat_port(entry_id: str, root: Path | None = None) -> str:
    for item in load_preset_catalog(root).entries:
        source = item.metadata.source_preset or {}
        if str(source.get("stratCollectionEntryId") or "") == entry_id:
            return item.preset.preset_id
    return ""


def port_strat_collection_entry(entry_id: str, root: Path | None = None) -> PresetMutationResult:
    layout = discover_layout(root)
    catalog = load_strat_collection(layout.root)
    entry = next((item for item in catalog.entries if item.entry_id == entry_id), None)
    if entry is None:
        raise ValueError(f"Неизвестная strat_collection стратегия: {entry_id}")
    plan = analyze_strat_port(entry, layout.root)
    if not plan.can_port:
        raise ValueError("Автопорт заблокирован: " + "; ".join(plan.unsupported[:8]))
    return create_owner_preset_from_runtime_args(
        plan.title,
        plan.runtime_args,
        root=layout.root,
        preset_id=("strat-" + re.sub(r"[^a-z0-9]+", "-", entry.entry_id.lower()).strip("-"))[:64].rstrip("-"),
        make_unique=True,
        action="strat-collection-ported",
        source_preset_extra={
            "engine": "nfqws2",
            "id": "strat-collection-port",
            "stratCollectionEntryId": entry.entry_id,
            "stratCollectionSource": entry.source_path.relative_to(layout.root).as_posix(),
            "legacyEngine": "winws/zapret1",
        },
        extra_notes=(
            "Conservative automatic port from bundled strat_collection; Windows capture flags were removed.",
            *plan.adaptations,
        ),
    )


__all__ = ["StratPortPlan", "analyze_strat_port", "find_existing_strat_port", "port_strat_collection_entry"]
