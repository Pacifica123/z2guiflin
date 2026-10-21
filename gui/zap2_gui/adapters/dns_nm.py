"""Смена DNS через NetworkManager (nmcli) с откатом.

Два режима:

* **временный** — ``nmcli device modify``: меняет только активное подключение устройства,
  профиль NetworkManager не трогает; откат — ``nmcli device reapply`` (или переподключение).
* **постоянный** — ``nmcli connection modify``: прежние значения профиля сохраняются в
  ``.zap2/dns/backup-<uuid>.json`` до первого изменения и восстанавливаются откатом.

Права даёт polkit NetworkManager (обычно без пароля для пользователя за компьютером).
Трогаются только настоящие подключения (ethernet, wifi); VPN, туннели и виртуальные
интерфейсы не меняются. Команды — списком аргументов, без shell.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
from typing import Callable, Sequence

from ..models.dns_catalog import DnsProvider

REAL_DEVICE_TYPES = ("ethernet", "wifi")
NMCLI_TIMEOUT_S = 30


@dataclass(frozen=True)
class Result:
    returncode: int
    stdout: str
    stderr: str = ""


Runner = Callable[[Sequence[str]], Result]


def run_nmcli(argv: Sequence[str]) -> Result:
    try:
        proc = subprocess.run(list(argv), capture_output=True, text=True, timeout=NMCLI_TIMEOUT_S)
    except FileNotFoundError:
        return Result(127, "", "nmcli не найден")
    except subprocess.TimeoutExpired:
        return Result(124, "", "nmcli не ответил")
    return Result(proc.returncode, proc.stdout, proc.stderr)


@dataclass(frozen=True)
class NmDevice:
    device: str
    device_type: str
    state: str
    connection: str


def _split_terse(line: str) -> list[str]:
    """Строка `nmcli -t`: поля через ':', внутри поля ':' экранировано как '\\:'."""

    fields, current, escape = [], [], False
    for char in line:
        if escape:
            current.append(char)
            escape = False
        elif char == "\\":
            escape = True
        elif char == ":":
            fields.append("".join(current))
            current = []
        else:
            current.append(char)
    fields.append("".join(current))
    return fields


def list_devices(runner: Runner = run_nmcli) -> tuple[NmDevice, ...]:
    result = runner(["nmcli", "-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "device", "status"])
    if result.returncode != 0:
        raise RuntimeError("nmcli device status: " + (result.stderr.strip() or str(result.returncode)))
    devices = []
    for line in result.stdout.splitlines():
        fields = _split_terse(line)
        if len(fields) >= 4:
            devices.append(NmDevice(*fields[:4]))
    return tuple(devices)


def real_connected_devices(runner: Runner = run_nmcli) -> tuple[NmDevice, ...]:
    return tuple(d for d in list_devices(runner) if d.device_type in REAL_DEVICE_TYPES and d.state.startswith("connected") and d.connection)


def current_dns(device: str, runner: Runner = run_nmcli) -> tuple[str, ...]:
    result = runner(["nmcli", "-t", "-f", "IP4.DNS,IP6.DNS", "device", "show", device])
    values = []
    for line in result.stdout.splitlines():
        key, _sep, value = line.partition(":")
        if key.startswith(("IP4.DNS", "IP6.DNS")) and value:
            values.append(value.replace("\\:", ":"))
    return tuple(values)


def connection_uuid(device: str, runner: Runner = run_nmcli) -> str:
    result = runner(["nmcli", "-g", "GENERAL.CON-UUID", "device", "show", device])
    uuid = result.stdout.strip()
    if result.returncode != 0 or not uuid:
        raise RuntimeError(f"не удалось узнать подключение устройства {device}")
    return uuid


def resolver_summary(resolv_conf: Path = Path("/etc/resolv.conf")) -> str:
    """Кто пишет /etc/resolv.conf — без root, только чтение."""

    try:
        if resolv_conf.is_symlink():
            target = os.readlink(resolv_conf)
            if "systemd/resolve" in target:
                return "systemd-resolved (resolv.conf — ссылка на " + target + ")"
            return "resolv.conf — ссылка на " + target
        text = resolv_conf.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return f"resolv.conf не читается: {exc}"
    if "NetworkManager" in text:
        return "NetworkManager пишет resolv.conf напрямую"
    if "127.0.0.53" in text:
        return "systemd-resolved (stub 127.0.0.53)"
    return "resolv.conf — обычный файл"


def dns_state_dir(root: Path) -> Path:
    return root / ".zap2" / "dns"


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _write_private(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def load_dns_state(root: Path) -> dict | None:
    try:
        return json.loads((dns_state_dir(root) / "state.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _dns_args(provider: DnsProvider, use_ipv6: bool) -> list[str]:
    args = ["ipv4.dns", ",".join(provider.ipv4), "ipv4.ignore-auto-dns", "yes"] if provider.ipv4 else []
    if use_ipv6 and provider.ipv6:
        args += ["ipv6.dns", ",".join(provider.ipv6), "ipv6.ignore-auto-dns", "yes"]
    return args


def _check(result: Result, what: str) -> None:
    if result.returncode != 0:
        raise RuntimeError(f"{what}: " + (result.stderr.strip() or result.stdout.strip() or str(result.returncode)))


def apply_dns(root: Path, device: str, provider: DnsProvider, *, persistent: bool = False, use_ipv6: bool = True,
              runner: Runner = run_nmcli) -> str:
    if not provider.plain_dns_works:
        raise ValueError(f"{provider.name} отвечает только по DoH/DoT — как обычный DNS его поставить нельзя")
    if not provider.ipv4 and not (use_ipv6 and provider.ipv6):
        raise ValueError(f"{provider.name}: нет адресов для выбранного режима")
    if device not in {d.device for d in real_connected_devices(runner)}:
        raise ValueError(f"{device}: не подключённое ethernet/wifi устройство; VPN и туннели не трогаются")
    previous = load_dns_state(root)
    if previous and previous.get("device") != device:
        raise ValueError(f"DNS уже изменён на {previous.get('device')}; сначала верните его")
    state_dir = dns_state_dir(root)
    uuid = connection_uuid(device, runner)
    if persistent:
        backup = state_dir / f"backup-{uuid}.json"
        if not backup.exists():
            got = runner(["nmcli", "-g", "ipv4.dns,ipv4.ignore-auto-dns,ipv6.dns,ipv6.ignore-auto-dns", "connection", "show", uuid])
            _check(got, "nmcli connection show")
            lines = (got.stdout.splitlines() + ["", "", "", ""])[:4]
            _write_private(backup, {"uuid": uuid, "ipv4.dns": lines[0], "ipv4.ignore-auto-dns": lines[1] or "no",
                                    "ipv6.dns": lines[2], "ipv6.ignore-auto-dns": lines[3] or "no", "savedAt": _now()})
        _check(runner(["nmcli", "connection", "modify", uuid, *_dns_args(provider, use_ipv6)]), "nmcli connection modify")
        _check(runner(["nmcli", "device", "reapply", device]), "nmcli device reapply")
    else:
        _check(runner(["nmcli", "device", "modify", device, *_dns_args(provider, use_ipv6)]), "nmcli device modify")
    mode = "persistent" if persistent else "temporary"
    if previous and previous.get("mode") == "persistent":
        mode = "persistent"  # бэкап профиля уже есть — откат должен его вернуть
    _write_private(state_dir / "state.json", {"device": device, "uuid": uuid, "mode": mode,
                                              "provider": provider.provider_id, "appliedAt": _now()})
    return f"DNS {provider.name} включён на {device} ({'постоянно' if persistent else 'до переподключения'})"


def revert_dns(root: Path, runner: Runner = run_nmcli) -> str:
    state = load_dns_state(root)
    if not state:
        return "DNS не менялся программой — откатывать нечего"
    device, uuid = str(state["device"]), str(state["uuid"])
    state_dir = dns_state_dir(root)
    if state.get("mode") == "persistent":
        backup_path = state_dir / f"backup-{uuid}.json"
        backup = json.loads(backup_path.read_text(encoding="utf-8"))
        _check(runner(["nmcli", "connection", "modify", uuid,
                       "ipv4.dns", backup["ipv4.dns"], "ipv4.ignore-auto-dns", backup["ipv4.ignore-auto-dns"],
                       "ipv6.dns", backup["ipv6.dns"], "ipv6.ignore-auto-dns", backup["ipv6.ignore-auto-dns"]]),
               "nmcli connection modify (откат)")
        _check(runner(["nmcli", "device", "reapply", device]), "nmcli device reapply")
        backup_path.unlink()
    else:
        _check(runner(["nmcli", "device", "reapply", device]), "nmcli device reapply")
    (state_dir / "state.json").unlink()
    return f"DNS на {device} возвращён к прежним настройкам"


__all__ = ["NmDevice", "Result", "apply_dns", "connection_uuid", "current_dns", "dns_state_dir", "list_devices",
           "load_dns_state", "real_connected_devices", "resolver_summary", "revert_dns", "run_nmcli"]
