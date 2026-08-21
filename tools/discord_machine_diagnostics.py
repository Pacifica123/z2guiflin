#!/usr/bin/env python3
"""Read-only Discord diagnostics for Arch-like Linux systems.

The script is intentionally standalone: Python 3.10+ standard library is enough.
It does not launch/kill Discord, change configuration, request sudo, or mutate the
firewall. Network probes are bounded and can be disabled with --no-network.
"""

from __future__ import annotations

import argparse
import base64
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import socket
import ssl
import struct
import subprocess
import sys
import time
from datetime import datetime, timezone
from typing import Any, Iterable
from urllib import error as urlerror
from urllib import request as urlrequest
from urllib.parse import urlsplit, urlunsplit

SCHEMA_VERSION = 1
SCRIPT_VERSION = "1.0"
DEFAULT_TIMEOUT = 4.0
MAX_COMMAND_OUTPUT = 24_000
MAX_LOG_BYTES = 96_000
MAX_LOG_MATCHES = 80

DISCORD_PACKAGE_NAMES = (
    "discord",
    "discord_arch_electron",
    "discord-ptb",
    "discord-canary",
    "discord-electron-openasar",
)
FLATPAK_APP_IDS = (
    "com.discordapp.Discord",
    "com.discordapp.DiscordCanary",
)
CONFIG_VARIANTS = (
    ("stable", "discord"),
    ("ptb", "discordptb"),
    ("canary", "discordcanary"),
)

ENDPOINTS = (
    {
        "id": "updater-manifest",
        "lane": "updater",
        "host": "updates.discord.com",
        "url": "https://updates.discord.com/distributions/app/manifests/latest?channel=stable&platform=linux&arch=x64",
        "http": True,
        "expect_json": True,
    },
    {
        "id": "updater-download",
        "lane": "updater",
        "host": "stable.dl2.discordapp.net",
        "http": False,
    },
    {
        "id": "app-api",
        "lane": "app-api",
        "host": "discord.com",
        "url": "https://discord.com/api/v10/gateway",
        "http": True,
        "expect_json": True,
    },
    {
        "id": "gateway",
        "lane": "gateway",
        "host": "gateway.discord.gg",
        "http": False,
        "websocket": True,
    },
    {
        "id": "cdn",
        "lane": "cdn-media",
        "host": "cdn.discordapp.com",
        "url": "https://cdn.discordapp.com/embed/avatars/0.png",
        "http": True,
    },
    {
        "id": "media",
        "lane": "cdn-media",
        "host": "media.discordapp.net",
        "http": False,
    },
    {
        "id": "invite",
        "lane": "secondary",
        "host": "discord.gg",
        "url": "https://discord.gg/",
        "http": True,
    },
)
CONTROL_ENDPOINT = {
    "id": "control-https",
    "lane": "control",
    "host": "example.com",
    "url": "https://example.com/",
    "http": True,
}

LOG_PATTERNS = (
    re.compile(r"checking[- ]for[- ]updates", re.I),
    re.compile(r"update[- ]check[- ]finished", re.I),
    re.compile(r"update failed|failed to update|host update is available|manual update required", re.I),
    re.compile(r"updater_bootstrap|updates\.discord\.com|stable\.dl2\.discordapp\.net", re.I),
    re.compile(r"ERR_(?:CONNECTION|TIMED_OUT|NAME_NOT_RESOLVED|CERT|NETWORK)|net::ERR_", re.I),
    re.compile(r"certificate|unknownissuer|invalidcertificate|tls|ssl", re.I),
    re.compile(r"gateway\.discord\.gg|FAST CONNECT|SESSION_ESTABLISHED|GatewaySocket", re.I),
    re.compile(r"slow network|network changed|connection reset|timed out", re.I),
    re.compile(r"living in the future|time traveller", re.I),
)
SENSITIVE_PATTERNS = (
    re.compile(r"(?i)(authorization\s*[:=]\s*)(\S+)"),
    re.compile(r"(?i)(token\s*[:=]\s*)([^\s,;]+)"),
    re.compile(r"(?i)(password\s*[:=]\s*)([^\s,;]+)"),
    re.compile(r"(?i)(proxy://)([^/@\s]+)@"),
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _trim(text: str, limit: int = MAX_COMMAND_OUTPUT) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "\n…[truncated]"


def sanitize_text(text: str, home: Path | None = None) -> str:
    """Remove common secrets and machine-identifying path details from copied output."""

    value = str(text).replace("\x00", " ")
    home = (home or Path.home()).resolve()
    home_text = str(home)
    if home_text and home_text != "/":
        value = value.replace(home_text, "~")
    user = os.environ.get("USER", "").strip()
    if user:
        value = value.replace(f"/home/{user}", "~")
    for pattern in SENSITIVE_PATTERNS:
        value = pattern.sub(lambda m: m.group(1) + "<redacted>", value)
    # Query strings frequently carry install identifiers or signed CDN tokens.
    value = re.sub(r"(https?://[^\s?]+)\?[^\s]+", r"\1?<query-redacted>", value)
    value = re.sub(r"(?i)(install_id=)[^&\s]+", r"\1<redacted>", value)
    return value


def safe_url(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "<query-redacted>" if parts.query else "", ""))


def run_command(argv: list[str], timeout: float = 4.0) -> dict[str, Any]:
    started = time.monotonic()
    try:
        completed = subprocess.run(
            argv,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=max(0.5, timeout),
            check=False,
            env={**os.environ, "LC_ALL": "C"},
        )
        return {
            "argv": argv,
            "available": True,
            "returncode": completed.returncode,
            "stdout": _trim(sanitize_text(completed.stdout)),
            "stderr": _trim(sanitize_text(completed.stderr)),
            "elapsedMs": round((time.monotonic() - started) * 1000),
        }
    except FileNotFoundError:
        return {"argv": argv, "available": False, "returncode": None, "stdout": "", "stderr": "command not found", "elapsedMs": 0}
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode(errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode(errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        return {
            "argv": argv,
            "available": True,
            "returncode": None,
            "stdout": _trim(sanitize_text(stdout)),
            "stderr": _trim(sanitize_text(stderr or f"timeout after {timeout:.1f}s")),
            "timedOut": True,
            "elapsedMs": round((time.monotonic() - started) * 1000),
        }
    except Exception as exc:
        return {
            "argv": argv,
            "available": True,
            "returncode": None,
            "stdout": "",
            "stderr": sanitize_text(f"{type(exc).__name__}: {exc}"),
            "elapsedMs": round((time.monotonic() - started) * 1000),
        }


def read_os_release() -> dict[str, str]:
    result: dict[str, str] = {}
    path = Path("/etc/os-release")
    try:
        for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if "=" not in raw or raw.lstrip().startswith("#"):
                continue
            key, value = raw.split("=", 1)
            result[key] = value.strip().strip('"')
    except OSError:
        pass
    return result


def collect_environment() -> dict[str, Any]:
    os_release = read_os_release()
    session_type = os.environ.get("XDG_SESSION_TYPE", "")
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "")
    proxy_env: dict[str, str] = {}
    for key in ("http_proxy", "https_proxy", "all_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY", "no_proxy"):
        raw = os.environ.get(key)
        if not raw:
            continue
        if "proxy" in key.lower() and "no_proxy" not in key.lower():
            parts = urlsplit(raw if "://" in raw else "proxy://" + raw)
            host = parts.hostname or "configured"
            port = f":{parts.port}" if parts.port else ""
            proxy_env[key] = f"{parts.scheme or 'proxy'}://{host}{port}"
        else:
            proxy_env[key] = sanitize_text(raw)[:300]

    commands: dict[str, Any] = {}
    for name, argv in (
        ("ipRoute", ["ip", "route", "show", "default"]),
        ("ip6Route", ["ip", "-6", "route", "show", "default"]),
        ("resolvectl", ["resolvectl", "status"]),
        ("timedatectl", ["timedatectl", "show", "-p", "NTPSynchronized", "-p", "Timezone", "-p", "LocalRTC"]),
    ):
        if shutil.which(argv[0]):
            commands[name] = run_command(argv, 4.0)

    resolv_conf = ""
    try:
        resolv_conf = sanitize_text(Path("/etc/resolv.conf").read_text(encoding="utf-8", errors="replace"))[:6000]
    except OSError as exc:
        resolv_conf = f"unreadable: {exc}"

    return {
        "platform": platform.platform(),
        "kernel": platform.release(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "osRelease": {k: os_release.get(k, "") for k in ("ID", "NAME", "VERSION_ID", "PRETTY_NAME", "ID_LIKE")},
        "sessionType": session_type,
        "desktop": desktop,
        "proxyEnvironment": proxy_env,
        "commands": commands,
        "resolvConf": resolv_conf,
    }


def parse_pacman_packages(text: str) -> list[dict[str, str]]:
    found: list[dict[str, str]] = []
    wanted = set(DISCORD_PACKAGE_NAMES)
    for line in text.splitlines():
        parts = line.split(maxsplit=1)
        if not parts:
            continue
        name = parts[0]
        if name in wanted or name.startswith("discord-") or "vesktop" in name.lower():
            found.append({"name": name, "version": parts[1] if len(parts) > 1 else ""})
    return found


def collect_installations(home: Path) -> dict[str, Any]:
    native: list[dict[str, Any]] = []
    pacman_all = run_command(["pacman", "-Q"], 5.0) if shutil.which("pacman") else None
    if pacman_all and pacman_all.get("returncode") == 0:
        for pkg in parse_pacman_packages(pacman_all.get("stdout", "")):
            detail = run_command(["pacman", "-Qi", pkg["name"]], 4.0)
            native.append({**pkg, "manager": "pacman/pamac", "detail": detail})

    pamac = None
    if shutil.which("pamac"):
        pamac = run_command(["pamac", "--version"], 3.0)

    flatpaks: list[dict[str, Any]] = []
    flatpak_list = None
    if shutil.which("flatpak"):
        flatpak_list = run_command(["flatpak", "list", "--app", "--columns=application,name,version,branch,origin,installation"], 6.0)
        if flatpak_list.get("returncode") == 0:
            for line in flatpak_list.get("stdout", "").splitlines():
                low = line.lower()
                if "discord" not in low and "vesktop" not in low:
                    continue
                columns = line.split("\t")
                app_id = columns[0].strip() if columns else line.split()[0]
                permissions = run_command(["flatpak", "info", "--show-permissions", app_id], 4.0)
                info = run_command(["flatpak", "info", app_id], 4.0)
                flatpaks.append({"appId": app_id, "columns": columns, "permissions": permissions, "info": info})

    snaps: list[dict[str, str]] = []
    if shutil.which("snap"):
        snap_list = run_command(["snap", "list"], 5.0)
        if snap_list.get("returncode") == 0:
            for line in snap_list.get("stdout", "").splitlines()[1:]:
                if "discord" in line.lower():
                    parts = line.split()
                    snaps.append({"name": parts[0], "version": parts[1] if len(parts) > 1 else ""})

    binaries: list[dict[str, str]] = []
    seen_paths: set[str] = set()
    for binary in ("discord", "Discord", "discord-canary", "discord-ptb", "vesktop"):
        path = shutil.which(binary)
        if path and path not in seen_paths:
            seen_paths.add(path)
            binaries.append({"name": binary, "path": sanitize_text(path, home)})

    desktop_entries: list[dict[str, str]] = []
    desktop_dirs = [home / ".local/share/applications", Path("/usr/share/applications")]
    for directory in desktop_dirs:
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.desktop")):
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if "discord" not in text.lower() and "vesktop" not in text.lower():
                continue
            name = ""
            exec_line = ""
            for line in text.splitlines():
                if line.startswith("Name=") and not name:
                    name = line.partition("=")[2]
                if line.startswith("Exec=") and not exec_line:
                    exec_line = line.partition("=")[2]
            desktop_entries.append({"path": sanitize_text(str(path), home), "name": name, "exec": sanitize_text(exec_line, home)})

    wrapper_text = ""
    wrapper = Path("/usr/bin/discord")
    if wrapper.is_file():
        try:
            wrapper_text = sanitize_text(wrapper.read_text(encoding="utf-8", errors="replace")[:12_000], home)
        except (OSError, UnicodeDecodeError):
            pass

    return {
        "native": native,
        "pamac": pamac,
        "flatpak": flatpaks,
        "flatpakList": flatpak_list,
        "snap": snaps,
        "binaries": binaries,
        "desktopEntries": desktop_entries,
        "nativeWrapper": wrapper_text,
        "zenityAvailable": bool(shutil.which("zenity")),
    }


def _proc_uptime_seconds(pid: int) -> float | None:
    try:
        stat_parts = Path(f"/proc/{pid}/stat").read_text().split()
        start_ticks = int(stat_parts[21])
        clk = os.sysconf(os.sysconf_names["SC_CLK_TCK"])
        uptime = float(Path("/proc/uptime").read_text().split()[0])
        return max(0.0, uptime - (start_ticks / clk))
    except (OSError, ValueError, IndexError, KeyError):
        return None


def collect_network_actors(home: Path) -> dict[str, Any]:
    tokens = (
        "nfqws", "nfqws2", "zapret", "xray", "v2ray", "sing-box", "singbox",
        "openvpn", "wg-quick", "wireguard", "tor", "redsocks", "tun2socks", "nekoray",
    )
    actors: list[dict[str, Any]] = []
    proc = Path("/proc")
    for entry in proc.iterdir() if proc.is_dir() else ():
        if not entry.name.isdigit():
            continue
        try:
            raw = (entry / "cmdline").read_bytes().replace(b"\x00", b" ").decode(errors="replace").strip()
            comm = (entry / "comm").read_text(errors="replace").strip()
        except OSError:
            continue
        combined = f"{comm} {raw}".lower()
        matched = next((token for token in tokens if token in combined), "")
        if not matched:
            continue
        actors.append({
            "pid": int(entry.name),
            "kind": matched,
            "comm": comm,
            "cmdline": sanitize_text(raw, home)[:2400],
        })

    commands: dict[str, Any] = {}
    for key, argv, timeout in (
        ("ipRule", ["ip", "rule", "show"], 4.0),
        ("nftRuleset", ["nft", "list", "ruleset"], 5.0),
        ("wg", ["wg", "show"], 4.0),
    ):
        if shutil.which(argv[0]):
            commands[key] = run_command(argv, timeout)
    return {"actors": actors, "commands": commands}


def collect_processes(home: Path) -> dict[str, Any]:
    matches: list[dict[str, Any]] = []
    proc = Path("/proc")
    for entry in proc.iterdir() if proc.is_dir() else ():
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        try:
            raw = (entry / "cmdline").read_bytes().replace(b"\x00", b" ").decode(errors="replace").strip()
            comm = (entry / "comm").read_text(errors="replace").strip()
        except OSError:
            continue
        combined = f"{comm} {raw}".lower()
        if not any(token in combined for token in ("discord", "updater_bootstrap", "vesktop")):
            continue
        age = _proc_uptime_seconds(pid)
        role = "updater" if "updater_bootstrap" in combined else "client"
        matches.append({
            "pid": pid,
            "role": role,
            "comm": comm,
            "cmdline": sanitize_text(raw, home)[:3000],
            "ageSeconds": round(age, 1) if age is not None else None,
        })

    sockets = None
    if shutil.which("ss") and matches:
        sockets_raw = run_command(["ss", "-H", "-tupn"], 5.0)
        pid_tokens = tuple(f"pid={item['pid']}," for item in matches)
        lines = [line for line in sockets_raw.get("stdout", "").splitlines() if any(token in line for token in pid_tokens)]
        sockets = {**sockets_raw, "stdout": "\n".join(lines)}
    return {"items": matches, "sockets": sockets}


def _allowed_settings(path: Path, home: Path) -> dict[str, Any]:
    result: dict[str, Any] = {"path": sanitize_text(str(path), home), "exists": path.is_file()}
    if not path.is_file():
        return result
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        if not isinstance(data, dict):
            result["error"] = "settings.json is not an object"
            return result
    except Exception as exc:
        result["error"] = sanitize_text(f"{type(exc).__name__}: {exc}", home)
        return result
    allow = ("SKIP_HOST_UPDATE", "MINIMIZE_TO_TRAY", "OPEN_ON_STARTUP", "BACKGROUND_COLOR")
    result["values"] = {key: data.get(key) for key in allow if key in data}
    result["keyCount"] = len(data)
    return result


def _candidate_config_roots(home: Path) -> list[tuple[str, Path]]:
    config_home = Path(os.environ.get("XDG_CONFIG_HOME", home / ".config")).expanduser()
    roots = [(channel, config_home / dirname) for channel, dirname in CONFIG_VARIANTS]
    roots.extend([
        ("flatpak-stable", home / ".var/app/com.discordapp.Discord/config/discord"),
        ("flatpak-canary", home / ".var/app/com.discordapp.DiscordCanary/config/discordcanary"),
    ])
    return roots


def _find_log_files(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    candidates: list[Path] = []
    patterns = ("*.log", "logs/*.log", "**/modules.log", "**/discord_debug.log", "**/renderer.log")
    seen: set[Path] = set()
    for pattern in patterns:
        for path in root.glob(pattern):
            try:
                resolved = path.resolve()
            except OSError:
                resolved = path
            if resolved in seen or not path.is_file():
                continue
            try:
                if len(path.relative_to(root).parts) > 5:
                    continue
            except ValueError:
                continue
            seen.add(resolved)
            candidates.append(path)
    return sorted(candidates, key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)[:12]


def _read_log_matches(path: Path, home: Path) -> list[str]:
    try:
        size = path.stat().st_size
        with path.open("rb") as handle:
            if size > MAX_LOG_BYTES:
                handle.seek(-MAX_LOG_BYTES, os.SEEK_END)
            text = handle.read(MAX_LOG_BYTES).decode("utf-8", errors="replace")
    except OSError:
        return []
    matches: list[str] = []
    for line in text.splitlines():
        if any(pattern.search(line) for pattern in LOG_PATTERNS):
            matches.append(sanitize_text(line, home)[:1600])
    return matches[-MAX_LOG_MATCHES:]


def collect_config_and_logs(home: Path) -> dict[str, Any]:
    configs: list[dict[str, Any]] = []
    logs: list[dict[str, Any]] = []
    for channel, root in _candidate_config_roots(home):
        if not root.exists():
            continue
        config_item: dict[str, Any] = {
            "channel": channel,
            "root": sanitize_text(str(root), home),
            "settings": _allowed_settings(root / "settings.json", home),
        }
        try:
            versions = sorted(
                item.name for item in root.iterdir()
                if item.is_dir() and re.fullmatch(r"\d+(?:\.\d+){2,3}", item.name)
            )
        except OSError:
            versions = []
        config_item["versionDirs"] = versions[-8:]
        configs.append(config_item)
        for path in _find_log_files(root):
            try:
                stat = path.stat()
                mtime = datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat()
            except OSError:
                stat = None
                mtime = ""
            matches = _read_log_matches(path, home)
            logs.append({
                "channel": channel,
                "path": sanitize_text(str(path), home),
                "size": stat.st_size if stat else None,
                "modifiedAt": mtime,
                "matches": matches,
            })

    journal = None
    if shutil.which("journalctl"):
        journal_raw = run_command([
            "journalctl", "--user", "--since=-2h", "--no-pager", "-o", "short-iso",
            "--grep=discord|updater_bootstrap|Discord",
        ], 6.0)
        lines = [sanitize_text(line, home) for line in journal_raw.get("stdout", "").splitlines() if any(p.search(line) for p in LOG_PATTERNS)]
        journal = {**journal_raw, "stdout": "\n".join(lines[-MAX_LOG_MATCHES:])}

    pacman_log: list[str] = []
    try:
        text = Path("/var/log/pacman.log").read_text(encoding="utf-8", errors="replace")
        pacman_log = [sanitize_text(line, home) for line in text.splitlines() if "discord" in line.lower()][-40:]
    except OSError:
        pass

    return {"configs": configs, "logs": logs, "journal": journal, "pacmanLog": pacman_log}


def collect_hosts_overrides() -> list[str]:
    try:
        lines = Path("/etc/hosts").read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    result: list[str] = []
    for raw in lines:
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if "discord" in line.lower():
            result.append(sanitize_text(line))
    return result


def resolve_host(host: str) -> dict[str, Any]:
    started = time.monotonic()
    try:
        records = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        addresses: list[str] = []
        for family, _socktype, _proto, _canonname, sockaddr in records:
            address = sockaddr[0]
            if address not in addresses:
                addresses.append(address)
        return {"ok": bool(addresses), "addresses": addresses[:12], "elapsedMs": round((time.monotonic() - started) * 1000)}
    except OSError as exc:
        return {"ok": False, "addresses": [], "error": f"{type(exc).__name__}: {exc}", "elapsedMs": round((time.monotonic() - started) * 1000)}


def tls_probe(host: str, address: str, timeout: float) -> dict[str, Any]:
    started = time.monotonic()
    family = socket.AF_INET6 if ":" in address else socket.AF_INET
    raw = socket.socket(family, socket.SOCK_STREAM)
    raw.settimeout(timeout)
    try:
        target: Any = (address, 443, 0, 0) if family == socket.AF_INET6 else (address, 443)
        raw.connect(target)
        context = ssl.create_default_context()
        with context.wrap_socket(raw, server_hostname=host) as tls:
            cert = tls.getpeercert()
            issuer = ""
            try:
                issuer = ", ".join("=".join(part) for row in cert.get("issuer", ()) for part in row)
            except Exception:
                issuer = ""
            return {
                "ok": True,
                "address": address,
                "tlsVersion": tls.version(),
                "cipher": tls.cipher()[0] if tls.cipher() else "",
                "issuer": issuer[:300],
                "elapsedMs": round((time.monotonic() - started) * 1000),
            }
    except Exception as exc:
        try:
            raw.close()
        except OSError:
            pass
        return {
            "ok": False,
            "address": address,
            "error": f"{type(exc).__name__}: {exc}",
            "elapsedMs": round((time.monotonic() - started) * 1000),
        }


def http_probe(url: str, timeout: float, expect_json: bool = False) -> dict[str, Any]:
    started = time.monotonic()
    req = urlrequest.Request(url, headers={"User-Agent": f"z2guiflin-discord-diagnostics/{SCRIPT_VERSION}", "Accept": "application/json,*/*;q=0.8"})
    try:
        with urlrequest.urlopen(req, timeout=timeout) as response:
            body = response.read(65_536)
            result: dict[str, Any] = {
                "ok": 200 <= response.status < 400,
                "status": response.status,
                "finalUrl": safe_url(response.geturl()),
                "contentType": response.headers.get("Content-Type", ""),
                "bytesRead": len(body),
                "elapsedMs": round((time.monotonic() - started) * 1000),
            }
            if expect_json:
                try:
                    parsed = json.loads(body.decode("utf-8", errors="replace"))
                    result["jsonOk"] = True
                    if isinstance(parsed, dict):
                        if "url" in parsed:
                            result["gatewayUrl"] = str(parsed["url"])
                        if "full" in parsed and isinstance(parsed["full"], dict):
                            result["hostVersion"] = parsed["full"].get("host_version")
                            result["manifestUrl"] = safe_url(str(parsed["full"].get("url", "")))
                except Exception as exc:
                    result["jsonOk"] = False
                    result["jsonError"] = f"{type(exc).__name__}: {exc}"
            return result
    except urlerror.HTTPError as exc:
        # HTTP response proves DNS/TCP/TLS/HTTP reachability even if path semantics reject us.
        return {
            "ok": 100 <= exc.code < 500,
            "status": exc.code,
            "finalUrl": safe_url(exc.geturl()),
            "error": f"HTTPError: {exc.code} {exc.reason}",
            "elapsedMs": round((time.monotonic() - started) * 1000),
        }
    except Exception as exc:
        return {
            "ok": False,
            "status": None,
            "finalUrl": safe_url(url),
            "error": f"{type(exc).__name__}: {exc}",
            "elapsedMs": round((time.monotonic() - started) * 1000),
        }


def websocket_handshake(host: str, timeout: float) -> dict[str, Any]:
    started = time.monotonic()
    key = base64.b64encode(os.urandom(16)).decode("ascii")
    try:
        raw = socket.create_connection((host, 443), timeout=timeout)
        context = ssl.create_default_context()
        with context.wrap_socket(raw, server_hostname=host) as tls:
            tls.settimeout(timeout)
            request = (
                "GET /?v=10&encoding=json HTTP/1.1\r\n"
                f"Host: {host}\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                f"Sec-WebSocket-Key: {key}\r\n"
                "Sec-WebSocket-Version: 13\r\n"
                f"User-Agent: z2guiflin-discord-diagnostics/{SCRIPT_VERSION}\r\n\r\n"
            )
            tls.sendall(request.encode("ascii"))
            data = b""
            while b"\r\n\r\n" not in data and len(data) < 8192:
                chunk = tls.recv(2048)
                if not chunk:
                    break
                data += chunk
            first = data.split(b"\r\n", 1)[0].decode("ascii", errors="replace")
            ok = " 101 " in f" {first} " or first.endswith(" 101 Switching Protocols")
            return {"ok": ok, "statusLine": first, "tlsVersion": tls.version(), "elapsedMs": round((time.monotonic() - started) * 1000)}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}", "elapsedMs": round((time.monotonic() - started) * 1000)}


def curl_http3_probe(timeout: float) -> dict[str, Any] | None:
    curl = shutil.which("curl")
    if not curl:
        return None
    version = run_command([curl, "--version"], 3.0)
    if "HTTP3" not in version.get("stdout", "") and "HTTP/3" not in version.get("stdout", ""):
        return {"available": False, "reason": "curl build has no HTTP/3 support", "version": version.get("stdout", "").splitlines()[0] if version.get("stdout") else ""}
    probe = run_command([
        curl, "--http3-only", "--silent", "--show-error", "--location", "--output", "/dev/null",
        "--write-out", "%{http_code} %{remote_ip} %{time_total}", "--max-time", str(max(1, int(timeout))),
        "https://discord.com/api/v10/gateway",
    ], timeout + 1.0)
    return {
        "available": True,
        "ok": probe.get("returncode") == 0,
        "result": probe.get("stdout", ""),
        "error": probe.get("stderr", ""),
        "elapsedMs": probe.get("elapsedMs"),
    }


def _endpoint_probe(spec: dict[str, Any], timeout: float) -> dict[str, Any]:
    host = str(spec["host"])
    dns = resolve_host(host)
    tls_results: list[dict[str, Any]] = []
    if dns.get("ok"):
        v4 = [a for a in dns.get("addresses", []) if ":" not in a][:1]
        v6 = [a for a in dns.get("addresses", []) if ":" in a][:1]
        for address in v4 + v6:
            tls_results.append(tls_probe(host, address, timeout))
    result: dict[str, Any] = {
        "id": spec["id"],
        "lane": spec["lane"],
        "host": host,
        "dns": dns,
        "tls": tls_results,
    }
    if spec.get("http") and spec.get("url"):
        result["http"] = http_probe(str(spec["url"]), timeout, bool(spec.get("expect_json")))
    if spec.get("websocket"):
        result["websocket"] = websocket_handshake(host, timeout)
    return result


def collect_network(timeout: float) -> dict[str, Any]:
    specs = list(ENDPOINTS) + [CONTROL_ENDPOINT]
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(8, len(specs))) as pool:
        future_map = {pool.submit(_endpoint_probe, spec, timeout): spec["id"] for spec in specs}
        results_by_id: dict[str, dict[str, Any]] = {}
        for future in concurrent.futures.as_completed(future_map):
            endpoint_id = future_map[future]
            try:
                results_by_id[endpoint_id] = future.result()
            except Exception as exc:
                results_by_id[endpoint_id] = {"id": endpoint_id, "error": f"{type(exc).__name__}: {exc}"}
    ordered = [results_by_id[spec["id"]] for spec in specs]
    return {"endpoints": ordered, "http3": curl_http3_probe(timeout)}


def _probe_ok(endpoint: dict[str, Any]) -> bool:
    if endpoint.get("http") is not None:
        return bool(endpoint.get("http", {}).get("ok"))
    if endpoint.get("websocket") is not None:
        return bool(endpoint.get("websocket", {}).get("ok"))
    tls = endpoint.get("tls") or []
    return any(item.get("ok") for item in tls)


def _finding(code: str, severity: str, title: str, detail: str, actions: Iterable[str]) -> dict[str, Any]:
    return {"code": code, "severity": severity, "title": title, "detail": detail, "actions": list(actions)}


def analyze(report: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    installs = report.get("installations", {})
    native = installs.get("native") or []
    flatpaks = installs.get("flatpak") or []
    snaps = installs.get("snap") or []
    if not native and not flatpaks and not snaps and not installs.get("binaries"):
        findings.append(_finding(
            "discord-not-found", "info", "Установка Discord не обнаружена",
            "В pacman/pamac, Flatpak, Snap, PATH и desktop entries не найден явный экземпляр Discord.",
            ["Если клиент установлен вручную, запустите probe из той же пользовательской сессии и проверьте desktop Exec/path."],
        ))
    elif len(native) + len(flatpaks) + len(snaps) > 1:
        findings.append(_finding(
            "multiple-installations", "warning", "Обнаружено несколько установок Discord",
            "Native/Flatpak/Snap экземпляры имеют разные каталоги, updater и sandbox. Ошибка одного экземпляра не доказывает ошибку другого.",
            ["Сопоставьте проблемный launcher с найденным Exec/path.", "Проверяйте native и Flatpak отдельно; не очищайте общий конфиг наугад."],
        ))

    wrapper = installs.get("nativeWrapper", "")
    if "updater_bootstrap" in wrapper and "--zenity" in wrapper and not installs.get("zenityAvailable"):
        findings.append(_finding(
            "native-zenity-missing", "warning", "Native launcher использует zenity, но zenity не найден",
            "Текущий /usr/bin/discord вызывает updater_bootstrap с --zenity. Отсутствующий zenity может ломать отображение bootstrap/update UI.",
            ["Установите zenity из репозитория Arch либо проверьте фактический launcher пакета перед повторным запуском."],
        ))

    processes = report.get("processes", {}).get("items", [])
    updaters = [item for item in processes if item.get("role") == "updater"]
    clients = [item for item in processes if item.get("role") == "client"]
    stale = [item for item in updaters if (item.get("ageSeconds") or 0) >= 30]
    if stale and not clients:
        age = max(float(item.get("ageSeconds") or 0) for item in stale)
        findings.append(_finding(
            "updater-stuck-process", "error", "Updater bootstrap выглядит зависшим",
            f"Есть updater_bootstrap старше {age:.0f} с, но основной Discord-процесс не обнаружен.",
            ["Сначала смотрите updater manifest/TLS ниже.", "Если сеть исправна, завершите stale updater и повторите запуск вручную из терминала для свежего лога."],
        ))

    overrides = report.get("hostsOverrides") or []
    if overrides:
        findings.append(_finding(
            "hosts-override", "error", "В /etc/hosts есть Discord-записи",
            "Статические Discord host overrides могут направлять клиент на устаревший или неверный адрес.",
            ["Проверьте и удалите только те Discord-записи /etc/hosts, которые вы добавляли намеренно и которые больше не нужны."],
        ))

    proxy_env = report.get("environment", {}).get("proxyEnvironment") or {}
    if proxy_env:
        findings.append(_finding(
            "proxy-environment", "warning", "В пользовательской сессии задан proxy environment",
            "HTTP(S)/ALL_PROXY может менять путь updater/API отдельно от остального трафика.",
            ["Сравните запуск Discord из чистой сессии без proxy env или убедитесь, что proxy пропускает updates.discord.com и gateway.discord.gg."],
        ))

    actors = report.get("networkActors", {}).get("actors") or []
    if actors:
        kinds = sorted({str(item.get("kind")) for item in actors if item.get("kind")})
        findings.append(_finding(
            "active-network-actors", "info", "Обнаружены активные сетевые обходы/туннели",
            "Во время probe работают: " + ", ".join(kinds) + ". Поэтому результат описывает текущий состав маршрутизации, а не обязательно чистый путь провайдера.",
            ["При сравнении direct vs Zapret/VPN повторяйте probe в двух явно известных состояниях и сравнивайте только изменившиеся lanes."],
        ))

    network = report.get("network") or {}
    endpoints = {item.get("id"): item for item in network.get("endpoints", [])}
    if endpoints:
        control_ok = _probe_ok(endpoints.get("control-https", {}))
        updater_ok = _probe_ok(endpoints.get("updater-manifest", {}))
        api_ok = _probe_ok(endpoints.get("app-api", {}))
        gateway_ok = _probe_ok(endpoints.get("gateway", {}))
        cdn_ok = _probe_ok(endpoints.get("cdn", {})) or _probe_ok(endpoints.get("media", {}))

        if control_ok and not updater_ok:
            detail = "Обычный контрольный HTTPS работает, но Discord updater manifest не проходит. Это локализует проблему в updater lane/маршруте Discord."
            findings.append(_finding(
                "updater-network-failure", "error", "Updater Discord недоступен при рабочем обычном HTTPS",
                detail,
                ["Проверьте DNS/TLS для updates.discord.com.", "Запустите Discord service target/blockcheck сначала по updater phase.", "Если через SOCKS/VLESS manifest открывается, проблема находится в прямом сетевом пути, а не в локальном GUI Discord."],
            ))
        if control_ok and updater_ok and not api_ok:
            findings.append(_finding(
                "api-network-failure", "error", "Updater доступен, но Discord API не проходит",
                "Bootstrap может завершиться, но основное окно/авторизация не смогут нормально загрузиться.",
                ["Проверяйте discord.com отдельно от updater host и не считайте успешный update-check доказательством работы приложения."],
            ))
        if control_ok and api_ok and not gateway_ok:
            findings.append(_finding(
                "gateway-network-failure", "error", "HTTPS API работает, Gateway WebSocket не устанавливается",
                "Это типичная отдельная ветка: страницы/API доступны, но постоянное соединение gateway.discord.gg ломается.",
                ["Проверяйте gateway.discord.gg как отдельный target.", "Сравните прямой путь с SOCKS/VLESS и с Zapret2 strategy, покрывающей gateway."],
            ))
        if control_ok and api_ok and gateway_ok and not cdn_ok:
            findings.append(_finding(
                "cdn-network-failure", "warning", "API/Gateway работают, CDN/media частично недоступны",
                "Текстовая часть Discord может работать, а аватары/вложения/media — нет.",
                ["Проверяйте cdn.discordapp.com и media.discordapp.net как отдельную CDN/media phase."],
            ))
        discord_results = [item for key, item in endpoints.items() if key != "control-https"]
        if not control_ok:
            findings.append(_finding(
                "general-network-failure", "error", "Не проходит даже контрольный HTTPS",
                "Проблема не локализована в Discord: сначала нужно восстановить базовый DNS/TCP/TLS путь текущей сети.",
                ["Проверьте route, DNS, proxy/VPN и системное время до настройки Zapret2."],
            ))
        elif discord_results and all(_probe_ok(item) for item in discord_results):
            findings.append(_finding(
                "discord-network-ok", "ok", "Текущий Discord network path проходит базовые проверки",
                "Updater manifest, API, Gateway WebSocket и CDN/TLS доступны в момент probe.",
                ["Если клиент всё ещё висит, приоритет смещается к конкретной установке, stale process, локальному config/cache или Electron/Flatpak окружению."],
            ))

    log_lines: list[str] = []
    for item in report.get("localEvidence", {}).get("logs", []):
        log_lines.extend(item.get("matches") or [])
    journal = report.get("localEvidence", {}).get("journal") or {}
    log_lines.extend(journal.get("stdout", "").splitlines())
    joined = "\n".join(log_lines[-300:])
    if re.search(r"UnknownIssuer|InvalidCertificate|ERR_CERT|certificate", joined, re.I):
        findings.append(_finding(
            "certificate-errors", "error", "В локальных логах есть ошибки сертификата/TLS",
            "Это может быть неверное системное время, TLS interception, корпоративный/провайдерский MITM или неверный trust store.",
            ["Проверьте timedatectl/NTP.", "Сравните issuer сертификата updates.discord.com с обычной сетью/VPN.", "Не отключайте проверку TLS как способ обхода."],
        ))
    if re.search(r"living in the future|time traveller", joined, re.I):
        findings.append(_finding(
            "clock-skew", "error", "Discord сообщает о некорректном времени",
            "Updater чувствителен к времени и срокам действия подписей/сертификатов.",
            ["Синхронизируйте системное время через systemd-timesyncd/chrony и повторите probe."],
        ))
    if re.search(r"checking[- ]for[- ]updates", joined, re.I) and not re.search(r"update[- ]check[- ]finished|no module updates available|launching", joined, re.I):
        findings.append(_finding(
            "log-update-loop", "warning", "Логи заканчиваются на стадии проверки обновлений",
            "В доступном фрагменте есть checking-for-updates без явного завершения update-check/launching.",
            ["Сопоставьте время лога с updater manifest probe; если manifest сейчас падает, сначала лечите сетевой updater lane."],
        ))

    session_type = str(report.get("environment", {}).get("sessionType", "")).lower()
    if session_type == "wayland" and flatpaks:
        for app in flatpaks:
            perms = (app.get("permissions") or {}).get("stdout", "")
            if "sockets=wayland" not in perms and "wayland;" not in perms and "x11" not in perms:
                findings.append(_finding(
                    "flatpak-display-permission", "warning", "Flatpak Discord не показывает явный Wayland/X11 socket permission",
                    "На Wayland это может мешать запуску окна независимо от сетевой доступности Discord.",
                    ["Проверьте flatpak permissions/override и сравните с штатным пакетом Flathub."],
                ))
                break

    if not findings:
        findings.append(_finding(
            "no-strong-signal", "info", "Однозначная причина механически не найдена",
            "Собранный контекст не содержит сильного сигнала. Это не означает, что проблема отсутствует.",
            ["Запустите probe именно во время зависания Discord и приложите технический блок вместе с HAR/Blockcheck наблюдением."],
        ))
    return findings


def summarize(findings: list[dict[str, Any]]) -> dict[str, Any]:
    rank = {"error": 4, "warning": 3, "info": 2, "ok": 1}
    primary = max(findings, key=lambda item: rank.get(str(item.get("severity")), 0))
    counts: dict[str, int] = {}
    for item in findings:
        sev = str(item.get("severity", "info"))
        counts[sev] = counts.get(sev, 0) + 1
    actions: list[str] = []
    for item in findings:
        for action in item.get("actions") or []:
            if action not in actions:
                actions.append(action)
    return {
        "severity": primary.get("severity", "info"),
        "title": primary.get("title", "Диагностика завершена"),
        "detail": primary.get("detail", ""),
        "counts": counts,
        "actions": actions[:8],
    }


def build_report(*, network: bool = True, timeout: float = DEFAULT_TIMEOUT) -> dict[str, Any]:
    home = Path.home()
    report: dict[str, Any] = {
        "schemaVersion": SCHEMA_VERSION,
        "tool": "discord_machine_diagnostics",
        "toolVersion": SCRIPT_VERSION,
        "createdAt": utc_now(),
        "readOnly": True,
        "privacy": {
            "doesNotReadTokensOrLocalStorage": True,
            "homePathRedacted": True,
            "urlQueriesRedactedInOutput": True,
            "networkProbesEnabled": bool(network),
        },
        "environment": collect_environment(),
        "installations": collect_installations(home),
        "processes": collect_processes(home),
        "networkActors": collect_network_actors(home),
        "hostsOverrides": collect_hosts_overrides(),
        "localEvidence": collect_config_and_logs(home),
        "network": collect_network(timeout) if network else {"skipped": True, "endpoints": [], "http3": None},
    }
    findings = analyze(report)
    report["findings"] = findings
    report["summary"] = summarize(findings)
    return report


def report_to_text(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    lines = [
        "Discord machine diagnostics",
        f"created: {report.get('createdAt', '')}",
        f"read-only: {'yes' if report.get('readOnly') else 'no'}",
        "",
        f"Итог: {summary.get('title', 'Диагностика завершена')}",
        str(summary.get("detail", "")),
        "",
        "Что попробовать:",
    ]
    actions = summary.get("actions") or []
    if actions:
        lines.extend(f"  - {item}" for item in actions)
    else:
        lines.append("  - нет однозначной рекомендации")

    lines.extend(["", "Найденные сигналы:"])
    for finding in report.get("findings", []):
        lines.append(f"  - [{finding.get('severity')}] {finding.get('code')}: {finding.get('title')}")
        lines.append(f"    {finding.get('detail')}")

    lines.extend(["", "Установки:"])
    installs = report.get("installations", {})
    for item in installs.get("native", []):
        lines.append(f"  - native {item.get('name')} {item.get('version')}")
    for item in installs.get("flatpak", []):
        lines.append(f"  - flatpak {item.get('appId')}")
    for item in installs.get("snap", []):
        lines.append(f"  - snap {item.get('name')} {item.get('version')}")
    if not any((installs.get("native"), installs.get("flatpak"), installs.get("snap"), installs.get("binaries"))):
        lines.append("  - не обнаружены")

    lines.extend(["", "Процессы:"])
    for item in report.get("processes", {}).get("items", []):
        lines.append(f"  - pid={item.get('pid')} role={item.get('role')} age={item.get('ageSeconds')}s {item.get('cmdline')}")
    if not report.get("processes", {}).get("items"):
        lines.append("  - Discord/updater процессы не обнаружены")

    actors = report.get("networkActors", {}).get("actors") or []
    lines.extend(["", "Сетевые процессы/обходы:"])
    if actors:
        lines.extend(f"  - {item.get('kind')} pid={item.get('pid')} {item.get('cmdline')}" for item in actors)
    else:
        lines.append("  - явные nfqws/xray/vpn/tor процессы не обнаружены")

    network = report.get("network", {})
    lines.extend(["", "Сеть:"])
    if network.get("skipped"):
        lines.append("  - network probes skipped")
    else:
        for endpoint in network.get("endpoints", []):
            status = "OK" if _probe_ok(endpoint) else "FAIL"
            dns = endpoint.get("dns", {})
            addr = ",".join(dns.get("addresses", [])[:3]) or "no-address"
            http = endpoint.get("http") or {}
            ws = endpoint.get("websocket") or {}
            extra = f" HTTP={http.get('status')}" if http else (f" WS={ws.get('statusLine', ws.get('error', ''))}" if ws else "")
            lines.append(f"  - {status} {endpoint.get('lane')}/{endpoint.get('host')} DNS={addr}{extra}")
        http3 = network.get("http3")
        if http3:
            lines.append(f"  - HTTP/3: {'OK' if http3.get('ok') else 'not proven'}; {http3.get('reason') or http3.get('result') or http3.get('error') or ''}")

    lines.extend(["", "Технический JSON (sanitized):", json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)])
    return "\n".join(lines).rstrip() + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only standalone Discord diagnostics for Arch-like Linux")
    parser.add_argument("--json", action="store_true", help="вывести только JSON для GUI/автоматизации")
    parser.add_argument("--no-network", action="store_true", help="не выполнять DNS/TCP/TLS/HTTP/WebSocket probes")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="timeout одного сетевого/CLI шага, сек")
    parser.add_argument("--output", type=Path, help="дополнительно сохранить sanitized результат в файл")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    timeout = max(1.0, min(15.0, float(args.timeout)))
    report = build_report(network=not args.no_network, timeout=timeout)
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n" if args.json else report_to_text(report)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
