"""Opt-in, transient Chrome DevTools Protocol GoogleVideo host capture.

Uses Chromium's private --remote-debugging-pipe (fds 3/4) with a fresh
0700 temporary profile. Does not connect to a user's normal browser profile,
open a localhost debugging port, save a HAR, or retain signed request URLs.
Only allowlisted GoogleVideo *hostnames* escape the CDP reader.
"""

from __future__ import annotations

import json
import os
import select
import shutil
import signal
import tempfile
import time
from dataclasses import dataclass
from typing import Callable
from urllib.parse import urlsplit

from .googlevideo_node import normalize_googlevideo_host

MAX_CDP_HOSTS = 12
MAX_CDP_SECONDS = 120
MAX_CDP_FRAME_BYTES = 1024 * 1024
CHROME_EXECUTABLES = ("chromium", "chromium-browser", "google-chrome-stable", "google-chrome", "brave-browser")


@dataclass(frozen=True)
class CdpCaptureResult:
    hosts: tuple[str, ...] = ()
    status: str = "finished"  # finished | timeout | browser-closed | cancelled

    def to_text(self) -> str:
        if not self.hosts:
            return f"CDP ({self.status}): CDN-хосты не обнаружены. Запусти воспроизведение в открытом браузере."
        return f"CDP ({self.status}): {len(self.hosts)} CDN-хостов: " + ", ".join(self.hosts)


def googlevideo_host_from_url(url: str) -> str:
    """Extract *only* a strict rr*/r* GoogleVideo host; never return URL tokens."""
    if not isinstance(url, str) or not url.startswith(("https://", "http://")):
        return ""
    try:
        parsed = urlsplit(url)
        # Forbid URL userinfo, ports and non-canonical hosts rather than
        # accidentally recognizing attacker-controlled URL variants.
        if parsed.username is not None or parsed.password is not None or parsed.port not in (None, 80, 443):
            return ""
        return normalize_googlevideo_host(parsed.hostname or "")
    except ValueError:
        return ""


class CdpHostCollector:
    """Pure protocol event reducer. No URLs or response bodies persist in state."""

    def __init__(self, max_hosts: int = MAX_CDP_HOSTS) -> None:
        self.max_hosts = max(1, min(MAX_CDP_HOSTS, int(max_hosts)))
        self._hosts: dict[str, None] = {}
        self._requests: dict[str, str] = {}  # requestId -> hostname only

    @property
    def hosts(self) -> tuple[str, ...]:
        return tuple(self._hosts)

    def ingest(self, message: dict) -> None:
        method = message.get("method")
        if method not in ("Network.requestWillBeSent", "Network.responseReceived", "Network.loadingFailed"):
            return
        params = message.get("params")
        if not isinstance(params, dict):
            return
        request_id = params.get("requestId")
        if method == "Network.loadingFailed":
            if isinstance(request_id, str):
                self._requests.pop(request_id, None)
            return
        value = params.get("request") if method == "Network.requestWillBeSent" else params.get("response")
        host = googlevideo_host_from_url(value.get("url", "")) if isinstance(value, dict) else ""
        if host and len(self._hosts) < self.max_hosts:
            self._hosts.setdefault(host, None)
        if isinstance(request_id, str) and host:
            if len(self._requests) >= 256:
                self._requests.clear()
            self._requests[request_id] = host


def detect_chromium() -> str | None:
    for name in CHROME_EXECUTABLES:
        path = shutil.which(name)
        if path:
            return path
    return None


def _launch_chromium(binary: str, profile: str) -> tuple[int, int, int]:
    """POSIX spawn avoids unsafe preexec_fn in a multithreaded Qt process.

    Chromium expects an input pipe on fd 3 and output pipe on fd 4.
    Parent-side fds are closed in the child *before* fd3/fd4 duplication.
    """
    if os.name != "posix" or not hasattr(os, "posix_spawn"):
        raise RuntimeError("CDP pipe доступен только на Linux/POSIX")
    parent_write = parent_read = child_read = child_write = -1
    try:
        child_read, parent_write = os.pipe()
        parent_read, child_write = os.pipe()
        # A source fd equal to 3/4 may make DUP2 a no-op; ensure it
        # survives exec even when Python created the pipe CLOEXEC.
        os.set_inheritable(child_read, True)
        os.set_inheritable(child_write, True)
        devnull = os.devnull
        actions = [
            (os.POSIX_SPAWN_OPEN, 0, devnull, os.O_RDONLY, 0o600),
            (os.POSIX_SPAWN_OPEN, 1, devnull, os.O_WRONLY, 0o600),
            (os.POSIX_SPAWN_OPEN, 2, devnull, os.O_WRONLY, 0o600),
            (os.POSIX_SPAWN_CLOSE, parent_write),
            (os.POSIX_SPAWN_CLOSE, parent_read),
            (os.POSIX_SPAWN_DUP2, child_read, 3),
            (os.POSIX_SPAWN_DUP2, child_write, 4),
        ]
        if child_read not in (3, 4):
            actions.append((os.POSIX_SPAWN_CLOSE, child_read))
        if child_write not in (3, 4):
            actions.append((os.POSIX_SPAWN_CLOSE, child_write))
        args = [
            binary,
            "--remote-debugging-pipe",
            f"--user-data-dir={profile}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-sync",
            "--new-window",
            "about:blank",
        ]
        pid = os.posix_spawn(binary, args, os.environ.copy(), file_actions=actions, setsid=True)
        os.close(child_read)
        os.close(child_write)
        return pid, parent_read, parent_write
    except BaseException:
        for fd in (parent_read, parent_write, child_read, child_write):
            if fd >= 0:
                try:
                    os.close(fd)
                except OSError:
                    pass
        raise


def _stop_chromium(pid: int) -> None:
    try:
        os.killpg(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    except OSError:
        pass
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        try:
            result, _ = os.waitpid(pid, os.WNOHANG)
        except ChildProcessError:
            return
        if result:
            return
        time.sleep(0.05)
    try:
        os.killpg(pid, signal.SIGKILL)
    except OSError:
        pass
    try:
        os.waitpid(pid, 0)
    except ChildProcessError:
        pass


def capture_browser_googlevideo(
    finished: Callable[[], bool],
    *,
    cancelled: Callable[[], bool] | None = None,
    ready: Callable[[str], None] | None = None,
    browser: str | None = None,
    max_seconds: float = MAX_CDP_SECONDS,
) -> CdpCaptureResult:
    """Open a disposable Chromium profile; collect CDN hostnames during playback.

    The browser launches about:blank. Once Network.enable is acknowledged, the
    attached page navigates to youtube.com; user initiates playback manually.
    Browser stderr/stdout are discarded (may contain URL credentials).
    """
    executable = browser or detect_chromium()
    if not executable:
        raise RuntimeError("Chromium/Chrome не найден в PATH. Установи Chromium для опционального CDP-сбора.")
    is_cancelled = cancelled or (lambda: False)
    deadline = time.monotonic() + max(1.0, min(float(max_seconds), MAX_CDP_SECONDS))
    collector = CdpHostCollector()
    pid = -1
    reader = writer = -1
    try:
        with tempfile.TemporaryDirectory(prefix="zap2-cdp-") as profile:
            os.chmod(profile, 0o700)
            pid, reader, writer = _launch_chromium(executable, profile)
            if ready:
                ready("CDP браузер запущен. Открой видео, затем нажми «Завершить CDP» в Blockcheck lab.")
            counter = 0
            actions: dict[int, tuple[str, str]] = {}
            sessions: set[str] = set()
            attaching: set[str] = set()
            navigated = False
            connected_at = time.monotonic()

            def send(method: str, params: dict | None = None, *, session: str = "", target: str = "") -> None:
                nonlocal counter
                counter += 1
                packet: dict = {"id": counter, "method": method, "params": params or {}}
                if session:
                    packet["sessionId"] = session
                actions[counter] = (method, target or session)
                payload = json.dumps(packet, separators=(",", ":")).encode("utf-8") + b"\x00"
                os.write(writer, payload)

            def attach(target_id: str) -> None:
                if not target_id or target_id in attaching:
                    return
                attaching.add(target_id)
                send("Target.attachToTarget", {"targetId": target_id, "flatten": True}, target=target_id)

            send("Target.setDiscoverTargets", {"discover": True})
            send("Target.setAutoAttach", {"autoAttach": True, "waitForDebuggerOnStart": False, "flatten": True})
            send("Target.getTargets")
            raw = b""
            status = "timeout"
            while True:
                if is_cancelled():
                    status = "cancelled"
                    break
                if finished():
                    status = "finished"
                    break
                if time.monotonic() >= deadline:
                    break
                if not navigated and time.monotonic() - connected_at > 15.0:
                    raise RuntimeError("CDP: не удалось подключиться к Network-потоку браузера")
                try:
                    exited, _ = os.waitpid(pid, os.WNOHANG)
                except ChildProcessError:
                    exited = pid
                if exited:
                    status = "browser-closed"
                    break
                readable, _, _ = select.select([reader], [], [], min(0.2, max(0.01, deadline - time.monotonic())))
                if not readable:
                    continue
                chunk = os.read(reader, 65536)
                if not chunk:
                    status = "browser-closed"
                    break
                raw += chunk
                if len(raw) > MAX_CDP_FRAME_BYTES:
                    raise RuntimeError("CDP: слишком большой кадр протокола; сбор прекращён")
                while b"\x00" in raw:
                    frame, raw = raw.split(b"\x00", 1)
                    if not frame:
                        continue
                    if len(frame) > MAX_CDP_FRAME_BYTES:
                        raise RuntimeError("CDP: слишком большой кадр протокола")
                    try:
                        message = json.loads(frame)
                    except (ValueError, UnicodeDecodeError):
                        continue
                    if not isinstance(message, dict):
                        continue
                    collector.ingest(message)
                    method = message.get("method")
                    params = message.get("params") or {}
                    if not isinstance(params, dict):
                        continue
                    if method == "Target.targetCreated":
                        info = params.get("targetInfo") or {}
                        if isinstance(info, dict) and info.get("type") == "page":
                            attach(str(info.get("targetId") or ""))
                    elif method == "Target.attachedToTarget":
                        sid = params.get("sessionId")
                        info = params.get("targetInfo") or {}
                        if isinstance(info, dict) and info.get("type") != "page":
                            continue
                        if isinstance(sid, str) and sid not in sessions:
                            sessions.add(sid)
                            send("Network.enable", session=sid)
                    elif method == "Target.detachedFromTarget":
                        sid = params.get("sessionId")
                        sessions.discard(sid)
                    elif isinstance(message.get("id"), int):
                        cmd, key = actions.pop(message["id"], ("", ""))
                        if "error" in message:
                            if cmd in ("Target.setAutoAttach", "Target.getTargets", "Network.enable"):
                                raise RuntimeError(f"CDP: команда {cmd} отклонена браузером")
                            continue
                        result = message.get("result") or {}
                        if not isinstance(result, dict):
                            continue
                        if cmd == "Target.getTargets":
                            for info in result.get("targetInfos", []):
                                if isinstance(info, dict) and info.get("type") == "page" and not info.get("attached"):
                                    attach(str(info.get("targetId") or ""))
                        elif cmd == "Target.attachToTarget":
                            sid = result.get("sessionId")
                            if isinstance(sid, str) and sid not in sessions:
                                sessions.add(sid)
                                send("Network.enable", session=sid)
                        elif cmd == "Network.enable" and not navigated:
                            navigated = True
                            if ready:
                                ready("CDP подключён к Network. Воспроизведи видео в браузере.")
                            send("Page.navigate", {"url": "https://www.youtube.com/"}, session=key)
            return CdpCaptureResult(collector.hosts, status)
    finally:
        for fd in (reader, writer):
            if fd >= 0:
                try:
                    os.close(fd)
                except OSError:
                    pass
        if pid > 0:
            _stop_chromium(pid)


__all__ = ["CdpCaptureResult", "CdpHostCollector", "capture_browser_googlevideo", "detect_chromium", "googlevideo_host_from_url"]
