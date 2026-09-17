"""Owned nftables integration for the bitwire-it aggregated IP blocklists.

Threat blocking is intentionally separate from zapret's NFQUEUE/hostlist policy:
this adapter owns a workspace-scoped nft table and only DROP rules. External list
data is never vendored. Updates build an immutable validated cache generation and
atomically switch a small pointer to it, so a failed/partial refresh cannot replace
the last-known-good generation.
"""
from __future__ import annotations

import fcntl
import hashlib
import io
import ipaddress
import json
import os
import shutil
import subprocess
import tempfile
import urllib.request
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, TextIO

from .runtime_owner import owned_nft_table_name, runtime_owner_identity
from .runtime_state import atomic_write_json
from ..project_paths import discover_layout

INBOUND_URL = "https://raw.githubusercontent.com/bitwire-it/ipblocklist/main/inbound.txt"
OUTBOUND_URL = "https://raw.githubusercontent.com/bitwire-it/ipblocklist/main/outbound.txt"
SCHEMA_VERSION = 2
MARKER = "zap2-security-blocklist-v2"
DEFAULT_INTERVAL_SECONDS = 7200
DEFAULT_DNS_EXCLUSIONS = (
    "1.1.1.1/32", "1.0.0.1/32", "8.8.8.8/32", "8.8.4.4/32",
    "9.9.9.9/32", "149.112.112.112/32",
    "2606:4700:4700::1111/128", "2606:4700:4700::1001/128",
    "2001:4860:4860::8888/128", "2001:4860:4860::8844/128",
    "2620:fe::fe/128", "2620:fe::9/128",
)
_CACHE_FILES = {
    ("inbound", 4): "inbound4.txt",
    ("inbound", 6): "inbound6.txt",
    ("outbound", 4): "outbound4.txt",
    ("outbound", 6): "outbound6.txt",
}


@dataclass(frozen=True)
class SecurityBlocklistResult:
    state: str
    message: str
    table_name: str
    config_path: Path
    state_path: Path
    inbound_count: int = 0
    outbound_count: int = 0
    used_last_known_good: bool = False

    @property
    def ok(self) -> bool:
        return self.state in {
            "disabled", "updated", "applied", "refreshed", "removed",
            "timer-installed", "timer-removed", "ready",
        }

    def to_text(self) -> str:
        return "\n".join([
            f"Security blocklist: {self.state}",
            f"message: {self.message}",
            f"nft table: {self.table_name}",
            f"inbound entries: {self.inbound_count}",
            f"outbound entries: {self.outbound_count}",
            f"last-known-good fallback: {'yes' if self.used_last_known_good else 'no'}",
            f"config: {self.config_path}",
            f"state: {self.state_path}",
        ])


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _paths(root: Path) -> tuple[Path, Path, Path, Path]:
    base = root / ".zap2" / "security" / "ipblocklist"
    return base, base / "config.json", base / "state.json", base / "cache.json"


def _generations_dir(root: Path) -> Path:
    return _paths(root)[0] / "generations"


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@contextmanager
def _security_lock(root: Path):
    lock_path = _paths(root)[0] / "security.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _default_config() -> dict[str, Any]:
    return {
        "schemaVersion": SCHEMA_VERSION,
        "enabled": False,
        # Inbound is intentionally opt-in: the upstream list is currently several
        # million entries and applies host-wide INPUT policy.
        "inboundEnabled": False,
        "outboundEnabled": True,
        "updateIntervalSeconds": DEFAULT_INTERVAL_SECONDS,
        "downloadTimeoutSeconds": 20,
        "maxDownloadBytes": 96 * 1024 * 1024,
        "minEntries": 100,
        "maxEntries": {"inbound": 6_000_000, "outbound": 1_000_000},
        "sources": {"inbound": INBOUND_URL, "outbound": OUTBOUND_URL},
        "dnsResolverExclusions": list(DEFAULT_DNS_EXCLUSIONS),
        "includeSystemResolvers": True,
        "licenseNotice": (
            "Aggregated list data is external; see bitwire-it/ipblocklist and original providers. "
            "Data is not vendored by Zap2 GUI."
        ),
    }


def _migrate_config(data: dict[str, Any]) -> dict[str, Any]:
    version = int(data.get("schemaVersion", 0) or 0)
    if version == SCHEMA_VERSION:
        return data
    if version == 1:
        migrated = _default_config()
        for key in (
            "enabled", "inboundEnabled", "outboundEnabled", "updateIntervalSeconds",
            "downloadTimeoutSeconds", "maxDownloadBytes", "minEntries", "sources",
            "dnsResolverExclusions", "includeSystemResolvers", "licenseNotice",
        ):
            if key in data:
                migrated[key] = data[key]
        migrated["schemaVersion"] = SCHEMA_VERSION
        return migrated
    raise ValueError("unsupported security blocklist config schema")


def ensure_security_blocklist_config(root: Path | None = None) -> Path:
    layout = discover_layout(root)
    base, config_path, _state, _cache = _paths(layout.root)
    base.mkdir(parents=True, exist_ok=True)
    _generations_dir(layout.root).mkdir(parents=True, exist_ok=True)
    if not config_path.exists():
        atomic_write_json(config_path, _default_config())
    else:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
        migrated = _migrate_config(raw)
        if migrated != raw:
            atomic_write_json(config_path, migrated)
    return config_path


def load_security_blocklist_config(root: Path | None = None) -> dict[str, Any]:
    path = ensure_security_blocklist_config(root)
    data = _migrate_config(json.loads(path.read_text(encoding="utf-8")))
    sources = data.get("sources")
    if not isinstance(sources, dict):
        raise ValueError("security blocklist sources must be an object")
    for key in ("inbound", "outbound"):
        url = str(sources.get(key, ""))
        if not url.startswith("https://"):
            raise ValueError(f"security blocklist source {key} must use https")
    max_entries = data.get("maxEntries")
    if not isinstance(max_entries, dict):
        raise ValueError("security blocklist maxEntries must be an object")
    for key in ("inbound", "outbound"):
        if int(max_entries.get(key, 0) or 0) < int(data.get("minEntries", 100)):
            raise ValueError(f"security blocklist maxEntries.{key} is below minEntries")
    return data


def set_security_blocklist_enabled(
    root: Path | None,
    enabled: bool,
    *,
    inbound: bool | None = None,
    outbound: bool | None = None,
) -> Path:
    layout = discover_layout(root)
    config_path = ensure_security_blocklist_config(layout.root)
    config = load_security_blocklist_config(layout.root)
    config["enabled"] = bool(enabled)
    if inbound is not None:
        config["inboundEnabled"] = bool(inbound)
    if outbound is not None:
        config["outboundEnabled"] = bool(outbound)
    if config["enabled"] and not (config.get("inboundEnabled") or config.get("outboundEnabled")):
        raise ValueError("security blocklist enabled policy requires inbound and/or outbound")
    atomic_write_json(config_path, config)
    return config_path


def _fetch(url: str, timeout: int, max_bytes: int) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "zap2-gui-security-blocklist/2"})
    with urllib.request.urlopen(request, timeout=timeout) as response:  # nosec B310: https enforced above
        content_type = str(response.headers.get("Content-Type", ""))
        if "text" not in content_type and "octet-stream" not in content_type and content_type:
            raise ValueError(f"unexpected Content-Type from blocklist source: {content_type}")
        data = response.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ValueError(f"blocklist source exceeds configured max bytes ({max_bytes})")
    return data


def _network_text(network: ipaddress._BaseNetwork) -> str:
    if network.prefixlen == network.max_prefixlen:
        return str(network.network_address)
    return str(network)


def _normalize_blob_to_files(
    blob: bytes,
    *,
    kind: str,
    directory: Path,
    min_entries: int,
    max_entries: int,
) -> dict[str, Any]:
    """Validate one upstream list in bounded-memory streaming fashion.

    bitwire-it publishes a sorted/collapsed list. We do not recollapse millions of
    entries in memory; each line is parsed independently and written into separate
    v4/v6 files. Exact adjacent duplicates are ignored. A configurable entry cap
    protects against an accidental source explosion.
    """

    directory.mkdir(parents=True, exist_ok=True)
    handles: dict[int, TextIO] = {}
    hashers = {4: hashlib.sha256(), 6: hashlib.sha256()}
    counts = {4: 0, 6: 0}
    previous: dict[int, str | None] = {4: None, 6: None}
    paths = {version: directory / _CACHE_FILES[(kind, version)] for version in (4, 6)}
    try:
        for version in (4, 6):
            handles[version] = paths[version].open("w", encoding="utf-8", newline="\n")
        for raw_line in io.BytesIO(blob):
            line = raw_line.decode("utf-8", errors="replace").split("#", 1)[0].strip()
            if not line:
                continue
            token = line.split()[0]
            try:
                network = ipaddress.ip_network(token, strict=False)
            except ValueError as exc:
                raise ValueError(f"{kind} blocklist contains an invalid network token: {token!r}") from exc
            version = network.version
            normalized = _network_text(network)
            if normalized == previous[version]:
                continue
            previous[version] = normalized
            counts[version] += 1
            if counts[4] + counts[6] > max_entries:
                raise ValueError(f"{kind} blocklist exceeds configured maxEntries={max_entries}")
            encoded = (normalized + "\n").encode("utf-8")
            handles[version].write(normalized + "\n")
            hashers[version].update(encoded)
    finally:
        for handle in handles.values():
            handle.close()
    total = counts[4] + counts[6]
    if total < min_entries:
        raise ValueError(f"{kind} blocklist validation failed: only {total} entries (< {min_entries})")
    return {
        "count": total,
        "ipv4Count": counts[4],
        "ipv6Count": counts[6],
        "files": {
            "4": {"name": paths[4].name, "sha256": hashers[4].hexdigest(), "bytes": paths[4].stat().st_size},
            "6": {"name": paths[6].name, "sha256": hashers[6].hexdigest(), "bytes": paths[6].stat().st_size},
        },
    }


def _fixture_generation(payload: dict[str, Any], directory: Path, enabled_kinds: tuple[str, ...]) -> dict[str, Any]:
    """Test/integration seam: materialize an already supplied validated-like payload."""

    lists = payload.get("lists")
    if not isinstance(lists, dict):
        raise ValueError("custom security blocklist fetcher must return a payload with lists")
    metadata: dict[str, Any] = {
        "schemaVersion": SCHEMA_VERSION,
        "fetchedAt": str(payload.get("fetchedAt") or _utc_now()),
        "sources": payload.get("sources", {}),
        "lists": {},
    }
    for kind in enabled_kinds:
        values = lists.get(kind)
        if not isinstance(values, list):
            raise ValueError(f"custom security blocklist fetcher omitted enabled list: {kind}")
        blob = ("\n".join(str(value) for value in values) + "\n").encode("utf-8")
        metadata["lists"][kind] = _normalize_blob_to_files(
            blob, kind=kind, directory=directory, min_entries=1,
            max_entries=max(1, len(values) + 10),
        )
    return metadata


def _enabled_kinds(config: dict[str, Any]) -> tuple[str, ...]:
    return tuple(kind for kind in ("inbound", "outbound") if bool(config.get(kind + "Enabled", False)))


def _generation_counts(metadata: dict[str, Any]) -> tuple[int, int]:
    lists = metadata.get("lists", {}) if isinstance(metadata, dict) else {}
    inbound = int((lists.get("inbound") or {}).get("count", 0)) if isinstance(lists, dict) else 0
    outbound = int((lists.get("outbound") or {}).get("count", 0)) if isinstance(lists, dict) else 0
    return inbound, outbound


def _active_generation(root: Path, config: dict[str, Any] | None = None) -> tuple[Path, dict[str, Any]]:
    _base, _config_path, _state_path, cache_path = _paths(root)
    if not cache_path.is_file():
        raise ValueError("security blocklist last-known-good cache отсутствует")
    pointer = json.loads(cache_path.read_text(encoding="utf-8"))
    if int(pointer.get("schemaVersion", 0) or 0) != SCHEMA_VERSION:
        raise ValueError("security blocklist cache schema is obsolete; refresh required")
    generation = str(pointer.get("activeGeneration", "")).strip()
    if not generation or "/" in generation or "\\" in generation or generation.startswith("."):
        raise ValueError("security blocklist cache generation pointer is invalid")
    generation_dir = _generations_dir(root) / generation
    metadata_path = generation_dir / "metadata.json"
    if not metadata_path.is_file():
        raise ValueError("security blocklist active generation metadata is missing")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    enabled = _enabled_kinds(config or load_security_blocklist_config(root))
    lists = metadata.get("lists", {})
    for kind in enabled:
        info = lists.get(kind) if isinstance(lists, dict) else None
        if not isinstance(info, dict):
            raise ValueError(f"last-known-good cache does not contain enabled {kind} list")
        for version in (4, 6):
            file_info = (info.get("files") or {}).get(str(version))
            if not isinstance(file_info, dict):
                raise ValueError(f"last-known-good cache metadata missing {kind} IPv{version}")
            path = generation_dir / str(file_info.get("name", ""))
            if not path.is_file():
                raise ValueError(f"last-known-good cache file missing: {path.name}")
            digest = _sha256_path(path)
            if digest != str(file_info.get("sha256", "")):
                raise ValueError(f"last-known-good cache integrity mismatch: {path.name}")
    return generation_dir, metadata


def _prune_old_generations(root: Path, active: str, keep: int = 2) -> None:
    generations = _generations_dir(root)
    candidates = sorted(
        (path for path in generations.iterdir() if path.is_dir() and not path.name.startswith(".")),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    kept = 0
    for path in candidates:
        if path.name == active or kept < keep - 1:
            kept += 1
            continue
        shutil.rmtree(path, ignore_errors=True)


def _update_security_blocklist_unlocked(root: Path | None = None, *, fetcher=None) -> SecurityBlocklistResult:
    layout = discover_layout(root)
    base, config_path, state_path, cache_path = _paths(layout.root)
    config = load_security_blocklist_config(layout.root)
    table = owned_nft_table_name(layout.root, "security", prefix="zap2sec")
    enabled_kinds = _enabled_kinds(config)
    if not enabled_kinds:
        raise ValueError("security blocklist has no enabled directions")

    generations = _generations_dir(layout.root)
    generations.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".stage-", dir=str(generations)))
    try:
        if fetcher is not None:
            metadata = _fixture_generation(fetcher(config), staging, enabled_kinds)
        else:
            timeout = max(1, min(120, int(config.get("downloadTimeoutSeconds", 20))))
            max_bytes = max(1024, min(256 * 1024 * 1024, int(config.get("maxDownloadBytes", 96 * 1024 * 1024))))
            min_entries = max(1, int(config.get("minEntries", 100)))
            max_entries_cfg = config.get("maxEntries", {})
            metadata = {"schemaVersion": SCHEMA_VERSION, "fetchedAt": _utc_now(), "sources": {}, "lists": {}}
            for kind in enabled_kinds:
                url = str(config["sources"][kind])
                blob = _fetch(url, timeout, max_bytes)
                metadata["sources"][kind] = {
                    "url": url,
                    "sha256": hashlib.sha256(blob).hexdigest(),
                    "rawBytes": len(blob),
                }
                metadata["lists"][kind] = _normalize_blob_to_files(
                    blob,
                    kind=kind,
                    directory=staging,
                    min_entries=min_entries,
                    max_entries=int(max_entries_cfg[kind]),
                )
        atomic_write_json(staging / "metadata.json", metadata)
        generation = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:10]}"
        final_dir = generations / generation
        staging.replace(final_dir)
        atomic_write_json(cache_path, {
            "schemaVersion": SCHEMA_VERSION,
            "marker": MARKER,
            "activeGeneration": generation,
            "activatedAt": _utc_now(),
        })
        _prune_old_generations(layout.root, generation)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    inbound_count, outbound_count = _generation_counts(metadata)
    atomic_write_json(state_path, {
        "schemaVersion": SCHEMA_VERSION,
        "marker": MARKER,
        "state": "updated",
        "updatedAt": _utc_now(),
        "tableName": table,
        "activeGeneration": generation,
        "counts": {"inbound": inbound_count, "outbound": outbound_count},
    })
    return SecurityBlocklistResult(
        "updated", "validated immutable cache generation activated atomically",
        table, config_path, state_path, inbound_count, outbound_count,
    )


def _run(argv: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)


def _owner_marker(root: Path) -> str:
    return f"zap2-security-owner:{runtime_owner_identity(root, 'security').owner_key}"


def _probe_owned_table(root: Path, table: str, runner) -> tuple[bool, bool]:
    result = runner(("nft", "list", "table", "inet", table))
    text = f"{getattr(result, 'stdout', '')}\n{getattr(result, 'stderr', '')}"
    if result.returncode != 0:
        lowered = text.lower()
        if "no such file" in lowered or "not found" in lowered:
            return False, True
        raise ValueError(f"cannot inspect nft table {table}: {text.strip()}")
    return True, _owner_marker(root) in text


def _system_resolver_exclusions() -> tuple[ipaddress._BaseNetwork, ...]:
    path = Path("/etc/resolv.conf")
    result: list[ipaddress._BaseNetwork] = []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ()
    for line in lines:
        parts = line.split()
        if len(parts) >= 2 and parts[0] == "nameserver":
            try:
                addr = ipaddress.ip_address(parts[1].split("%", 1)[0])
            except ValueError:
                continue
            result.append(ipaddress.ip_network(f"{addr}/{addr.max_prefixlen}"))
    return tuple(result)


def _resolver_exclusions(config: dict[str, Any]) -> tuple[ipaddress._BaseNetwork, ...]:
    values: list[ipaddress._BaseNetwork] = []
    for raw in config.get("dnsResolverExclusions", []):
        try:
            values.append(ipaddress.ip_network(str(raw), strict=False))
        except ValueError as exc:
            raise ValueError(f"invalid DNS resolver exclusion: {raw}") from exc
    if config.get("includeSystemResolvers", True):
        values.extend(_system_resolver_exclusions())
    unique: dict[tuple[int, int, int], ipaddress._BaseNetwork] = {}
    for network in values:
        unique[(network.version, int(network.network_address), network.prefixlen)] = network
    return tuple(unique[key] for key in sorted(unique))


def _iter_cache_values(generation_dir: Path, metadata: dict[str, Any], kind: str, version: int) -> Iterator[str]:
    info = metadata["lists"][kind]["files"][str(version)]
    path = generation_dir / info["name"]
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            value = line.strip()
            if value:
                yield value


def _write_elements(handle: TextIO, table: str, set_name: str, values: Iterable[str], *, chunk_size: int = 1500) -> int:
    chunk: list[str] = []
    count = 0
    for value in values:
        chunk.append(value)
        count += 1
        if len(chunk) >= chunk_size:
            handle.write(f"add element inet {table} {set_name} {{ {', '.join(chunk)} }}\n")
            chunk.clear()
    if chunk:
        handle.write(f"add element inet {table} {set_name} {{ {', '.join(chunk)} }}\n")
    return count


def _write_nft_transaction(
    root: Path,
    table: str,
    generation_dir: Path,
    metadata: dict[str, Any],
    config: dict[str, Any],
    table_exists: bool,
    destination: Path,
) -> None:
    identity = runtime_owner_identity(root, "security")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write((f"flush table inet {table}\n" if table_exists else f"add table inet {table}\n"))
        handle.write(f"add chain inet {table} owner_meta\n")
        handle.write(f'add rule inet {table} owner_meta counter comment "{_owner_marker(root)}"\n')

        exclusions = _resolver_exclusions(config)
        for version, nft_type, selector in ((4, "ipv4_addr", "ip"), (6, "ipv6_addr", "ip6")):
            values = [_network_text(net) for net in exclusions if net.version == version]
            if not values:
                continue
            set_name = f"dns_exclusions{version}"
            handle.write(f"add set inet {table} {set_name} {{ type {nft_type}; flags interval; auto-merge; }}\n")
            _write_elements(handle, table, set_name, values)

        for kind in _enabled_kinds(config):
            info = metadata.get("lists", {}).get(kind)
            if not isinstance(info, dict):
                raise ValueError(f"active cache generation is missing enabled {kind} list")
            chain = "security_input" if kind == "inbound" else "security_output"
            hook = "input" if kind == "inbound" else "output"
            handle.write(f"add chain inet {table} {chain} {{ type filter hook {hook} priority -10; policy accept; }}\n")
            direction = "saddr" if kind == "inbound" else "daddr"
            uid_scope = "" if kind == "inbound" else f"meta skuid {identity.uid} "
            for version, nft_type, selector in ((4, "ipv4_addr", "ip"), (6, "ipv6_addr", "ip6")):
                count = int(info.get("ipv4Count" if version == 4 else "ipv6Count", 0))
                if count <= 0:
                    continue
                exclusion_set = f"dns_exclusions{version}"
                if any(net.version == version for net in exclusions):
                    handle.write(
                        f'add rule inet {table} {chain} {uid_scope}{selector} {direction} @{exclusion_set} '
                        f'counter accept comment "zap2-security:dns-exclusion-{kind}{version}"\n'
                    )
                set_name = f"{kind}{version}"
                handle.write(f"add set inet {table} {set_name} {{ type {nft_type}; flags interval; auto-merge; }}\n")
                written = _write_elements(handle, table, set_name, _iter_cache_values(generation_dir, metadata, kind, version))
                if written != count:
                    raise ValueError(f"active cache count mismatch for {kind} IPv{version}: metadata={count}, file={written}")
                handle.write(
                    f'add rule inet {table} {chain} {uid_scope}{selector} {direction} @{set_name} '
                    f'counter drop comment "zap2-security:{kind}{version}"\n'
                )


def _apply_security_blocklist_unlocked(root: Path | None = None, *, runner=None, allow_without_root: bool = False) -> SecurityBlocklistResult:
    layout = discover_layout(root)
    _base, config_path, state_path, _cache_path = _paths(layout.root)
    config = load_security_blocklist_config(layout.root)
    table = owned_nft_table_name(layout.root, "security", prefix="zap2sec")
    if not config.get("enabled", False):
        return _remove_security_blocklist_unlocked(layout.root, runner=runner, allow_without_root=allow_without_root)
    generation_dir, metadata = _active_generation(layout.root, config)
    runner = runner or _run
    if not allow_without_root and getattr(os, "geteuid", lambda: 1)() != 0:
        raise ValueError("security blocklist apply requires root/CAP_NET_ADMIN")
    exists, owned = _probe_owned_table(layout.root, table, runner)
    if exists and not owned:
        raise ValueError(f"nft table {table} exists without our owner marker; overwrite refused")

    tx_dir = layout.root / ".zap2" / "security" / "ipblocklist" / "transactions"
    batch_path = tx_dir / "apply.nft"
    _write_nft_transaction(layout.root, table, generation_dir, metadata, config, exists, batch_path)
    check = runner(("nft", "--check", "-f", str(batch_path)))
    if check.returncode != 0:
        raise ValueError(f"nft --check failed: {getattr(check, 'stderr', '') or getattr(check, 'stdout', '')}")
    result = runner(("nft", "-f", str(batch_path)))
    if result.returncode != 0:
        raise ValueError(f"nft apply failed: {getattr(result, 'stderr', '') or getattr(result, 'stdout', '')}")

    inbound_count, outbound_count = _generation_counts(metadata)
    pointer = json.loads(_paths(layout.root)[3].read_text(encoding="utf-8"))
    atomic_write_json(state_path, {
        "schemaVersion": SCHEMA_VERSION,
        "marker": MARKER,
        "state": "applied",
        "updatedAt": _utc_now(),
        "tableName": table,
        "ownerMarker": _owner_marker(layout.root),
        "activeGeneration": pointer.get("activeGeneration"),
        "counts": {"inbound": inbound_count, "outbound": outbound_count},
    })
    return SecurityBlocklistResult(
        "applied", "validated last-known-good generation applied in an isolated owned nft table",
        table, config_path, state_path, inbound_count, outbound_count,
    )


def _remove_security_blocklist_unlocked(root: Path | None = None, *, runner=None, allow_without_root: bool = False) -> SecurityBlocklistResult:
    layout = discover_layout(root)
    _base, config_path, state_path, _cache_path = _paths(layout.root)
    table = owned_nft_table_name(layout.root, "security", prefix="zap2sec")
    runner = runner or _run
    if not allow_without_root and getattr(os, "geteuid", lambda: 1)() != 0:
        raise ValueError("security blocklist removal requires root/CAP_NET_ADMIN")
    exists, owned = _probe_owned_table(layout.root, table, runner)
    if exists and not owned:
        raise ValueError(f"nft table {table} owner marker mismatch; delete refused")
    if exists:
        path = layout.root / ".zap2" / "security" / "ipblocklist" / "transactions" / "remove.nft"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"delete table inet {table}\n", encoding="utf-8")
        check = runner(("nft", "--check", "-f", str(path)))
        if check.returncode != 0:
            raise ValueError("nft remove preflight failed")
        result = runner(("nft", "-f", str(path)))
        if result.returncode != 0:
            raise ValueError("nft remove failed")
    atomic_write_json(state_path, {
        "schemaVersion": SCHEMA_VERSION, "marker": MARKER, "state": "removed",
        "updatedAt": _utc_now(), "tableName": table,
    })
    return SecurityBlocklistResult("removed", "owned security table absent/removed", table, config_path, state_path)


def update_security_blocklist(root: Path | None = None, *, fetcher=None) -> SecurityBlocklistResult:
    layout = discover_layout(root)
    with _security_lock(layout.root):
        return _update_security_blocklist_unlocked(layout.root, fetcher=fetcher)


def apply_security_blocklist(root: Path | None = None, *, runner=None, allow_without_root: bool = False) -> SecurityBlocklistResult:
    layout = discover_layout(root)
    with _security_lock(layout.root):
        return _apply_security_blocklist_unlocked(layout.root, runner=runner, allow_without_root=allow_without_root)


def remove_security_blocklist(root: Path | None = None, *, runner=None, allow_without_root: bool = False) -> SecurityBlocklistResult:
    layout = discover_layout(root)
    with _security_lock(layout.root):
        return _remove_security_blocklist_unlocked(layout.root, runner=runner, allow_without_root=allow_without_root)


def refresh_security_blocklist(root: Path | None = None, *, runner=None, fetcher=None, allow_without_root: bool = False) -> SecurityBlocklistResult:
    layout = discover_layout(root)
    _base, config_path, state_path, _cache_path = _paths(layout.root)
    config = load_security_blocklist_config(layout.root)
    table = owned_nft_table_name(layout.root, "security", prefix="zap2sec")
    if not config.get("enabled", False):
        return remove_security_blocklist(layout.root, runner=runner, allow_without_root=allow_without_root)
    fallback = False
    try:
        update_security_blocklist(layout.root, fetcher=fetcher)
    except Exception as exc:
        try:
            _active_generation(layout.root, config)
        except Exception as cache_exc:
            raise ValueError(f"blocklist update failed and no valid last-known-good cache exists: {exc}; cache: {cache_exc}") from exc
        fallback = True
        atomic_write_json(state_path, {
            "schemaVersion": SCHEMA_VERSION, "marker": MARKER, "state": "update-failed-lkg-retained",
            "updatedAt": _utc_now(), "tableName": table, "error": str(exc),
        })
    result = apply_security_blocklist(layout.root, runner=runner, allow_without_root=allow_without_root)
    return SecurityBlocklistResult(
        "refreshed",
        "security blocklist refreshed" if not fallback else "update failed; valid last-known-good generation retained and re-applied",
        table, config_path, state_path, result.inbound_count, result.outbound_count, fallback,
    )


def security_blocklist_status(root: Path | None = None) -> SecurityBlocklistResult:
    layout = discover_layout(root)
    _base, config_path, state_path, _cache_path = _paths(layout.root)
    config = load_security_blocklist_config(layout.root)
    table = owned_nft_table_name(layout.root, "security", prefix="zap2sec")
    inbound_count = outbound_count = 0
    cache_note = "no validated cache generation"
    try:
        _generation_dir, metadata = _active_generation(layout.root, config)
        inbound_count, outbound_count = _generation_counts(metadata)
        cache_note = "validated cache generation available"
    except Exception as exc:
        cache_note = f"cache unavailable: {exc}"
    state = "ready" if config.get("enabled", False) else "disabled"
    message = (
        f"policy enabled; refresh requires explicit privileged action/timer; {cache_note}"
        if state == "ready" else f"policy disabled (fail-safe default); {cache_note}"
    )
    return SecurityBlocklistResult(state, message, table, config_path, state_path, inbound_count, outbound_count)


def _timer_names(root: Path) -> tuple[str, str]:
    digest = runtime_owner_identity(root, "security").workspace_digest[:10]
    return f"zap2-ipblocklist-{digest}.service", f"zap2-ipblocklist-{digest}.timer"


def _systemd_quote(value: str | Path) -> str:
    text = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{text}"'


def security_blocklist_timer_plan(root: Path | None = None) -> tuple[str, str, str, str]:
    layout = discover_layout(root)
    service_name, timer_name = _timer_names(layout.root)
    python = Path(os.path.realpath(os.environ.get("ZAP2_PYTHON", "/usr/bin/python3")))
    config = load_security_blocklist_config(layout.root)
    interval = int(config.get("updateIntervalSeconds", DEFAULT_INTERVAL_SECONDS))
    if interval < 3600:
        raise ValueError("security blocklist updateIntervalSeconds must be at least 3600")
    service = "\n".join([
        "[Unit]",
        f"Description=Zap2 security IP blocklist refresh ({runtime_owner_identity(layout.root, 'security').workspace_digest})",
        "After=network-online.target",
        "Wants=network-online.target",
        "",
        "[Service]",
        "Type=oneshot",
        f"WorkingDirectory={_systemd_quote(layout.root)}",
        f"Environment={_systemd_quote('PYTHONPATH=' + str(layout.root / 'gui'))}",
        "Environment=PYTHONDONTWRITEBYTECODE=1",
        "UMask=0077",
        f"ExecStart={_systemd_quote(python)} -m zap2_gui.app --security-blocklist-refresh",
        "NoNewPrivileges=true",
        "PrivateTmp=true",
        "ProtectHome=read-only",
        "ProtectSystem=strict",
        f"ReadWritePaths={_systemd_quote(layout.root / '.zap2')}",
        "",
    ])
    timer = "\n".join([
        "[Unit]",
        "Description=Periodic Zap2 security IP blocklist refresh",
        "",
        "[Timer]",
        "OnBootSec=5min",
        f"OnUnitActiveSec={interval}s",
        "RandomizedDelaySec=10min",
        "Persistent=true",
        f"Unit={service_name}",
        "",
        "[Install]",
        "WantedBy=timers.target",
        "",
    ])
    return service_name, timer_name, service, timer


def _write_unit_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    temp = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp, 0o644)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def install_security_blocklist_timer(
    root: Path | None = None,
    *,
    systemd_dir: Path = Path("/etc/systemd/system"),
    runner=None,
    allow_without_root: bool = False,
) -> SecurityBlocklistResult:
    layout = discover_layout(root)
    if not allow_without_root and getattr(os, "geteuid", lambda: 1)() != 0:
        raise ValueError("timer install requires root")
    runner = runner or _run
    _base, config_path, state_path, _cache = _paths(layout.root)
    if not config_path.is_file():
        raise ValueError("create/enable security blocklist config as the workspace owner before installing the root timer")
    service_name, timer_name, service, timer = security_blocklist_timer_plan(layout.root)
    service_path = systemd_dir / service_name
    timer_path = systemd_dir / timer_name
    _write_unit_atomic(service_path, service)
    _write_unit_atomic(timer_path, timer)
    try:
        for argv in (("systemctl", "daemon-reload"), ("systemctl", "enable", "--now", timer_name)):
            result = runner(argv)
            if result.returncode != 0:
                raise ValueError(f"systemd command failed: {' '.join(argv)}: {getattr(result, 'stderr', '')}")
    except Exception:
        service_path.unlink(missing_ok=True)
        timer_path.unlink(missing_ok=True)
        runner(("systemctl", "daemon-reload"))
        raise
    table = owned_nft_table_name(layout.root, "security", prefix="zap2sec")
    return SecurityBlocklistResult(
        "timer-installed", f"installed {timer_name}; policy remains controlled by config.enabled",
        table, config_path, state_path,
    )


def remove_security_blocklist_timer(
    root: Path | None = None,
    *,
    systemd_dir: Path = Path("/etc/systemd/system"),
    runner=None,
    allow_without_root: bool = False,
) -> SecurityBlocklistResult:
    layout = discover_layout(root)
    if not allow_without_root and getattr(os, "geteuid", lambda: 1)() != 0:
        raise ValueError("timer removal requires root")
    runner = runner or _run
    _base, config_path, state_path, _cache = _paths(layout.root)
    service_name, timer_name = _timer_names(layout.root)
    disable = runner(("systemctl", "disable", "--now", timer_name))
    # Missing/non-enabled timer is idempotent; files are still removed below.
    if disable.returncode != 0:
        text = f"{getattr(disable, 'stdout', '')}\n{getattr(disable, 'stderr', '')}".lower()
        if not any(token in text for token in ("not loaded", "not found", "does not exist", "not enabled")):
            raise ValueError(f"systemd timer disable failed: {text.strip()}")
    (systemd_dir / timer_name).unlink(missing_ok=True)
    (systemd_dir / service_name).unlink(missing_ok=True)
    reload_result = runner(("systemctl", "daemon-reload"))
    if reload_result.returncode != 0:
        raise ValueError(f"systemctl daemon-reload failed after timer removal: {getattr(reload_result, 'stderr', '')}")
    table = owned_nft_table_name(layout.root, "security", prefix="zap2sec")
    return SecurityBlocklistResult("timer-removed", f"removed {timer_name}; firewall policy unchanged", table, config_path, state_path)


__all__ = [
    "INBOUND_URL", "OUTBOUND_URL", "SecurityBlocklistResult",
    "apply_security_blocklist", "ensure_security_blocklist_config",
    "install_security_blocklist_timer", "load_security_blocklist_config",
    "refresh_security_blocklist", "remove_security_blocklist",
    "remove_security_blocklist_timer", "security_blocklist_status",
    "security_blocklist_timer_plan", "set_security_blocklist_enabled",
    "update_security_blocklist",
]
