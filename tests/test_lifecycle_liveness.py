from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from zap2_gui import distribution
from zap2_gui.distribution import active_runtime_records, confirm_runtime_stopped, ensure_workspace, runtime_record_activity


def _tiny(tmp: Path, name: str, version: str) -> Path:
    import hashlib

    root = tmp / name
    (root / "tools").mkdir(parents=True)
    (root / "tools/managed").write_text(name)
    records = {"tools/managed": {"sha256": hashlib.sha256(name.encode()).hexdigest(), "mode": 0o644}}
    digest = hashlib.sha256(json.dumps(records, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    (root / "RELEASE_MANIFEST.json").write_text(json.dumps({"schemaVersion": 1, "version": version, "releaseDigest": digest, "files": records}))
    return root


def _session(ws: Path, data: dict, name: str = "default.session.json") -> Path:
    path = ws / ".zap2/runtime/sessions" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))
    return path


def _dead_pid() -> int:
    pid = 4_000_000
    while True:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return pid
        except PermissionError:
            pass
        pid -= 1


def test_dead_pid_session_does_not_block_upgrade(tmp_path: Path) -> None:
    old, new = _tiny(tmp_path, "old", "1.2.0"), _tiny(tmp_path, "new", "1.3.0")
    ws = tmp_path / "data/workspace"
    ensure_workspace(old, ws)
    record = _session(ws, {"state": "stale", "pid": _dead_pid()})
    assert ensure_workspace(new, ws)["version"] == "1.3.0"
    # Запись сохранена как есть: обновление ничего не удаляет из .zap2.
    assert json.loads(record.read_text())["state"] == "stale"


def test_record_from_previous_boot_does_not_block(tmp_path: Path, monkeypatch) -> None:
    ws = tmp_path / "ws"
    path = _session(ws, {"state": "applied"}, "default.owner-rules.json")
    assert runtime_record_activity(path, boot_time=time.time() - 3600) == "state=applied"
    old = time.time() - 7200
    os.utime(path, (old, old))
    assert runtime_record_activity(path, boot_time=time.time() - 3600) is None


def test_reused_pid_of_foreign_process_is_not_our_runtime(tmp_path: Path) -> None:
    path = _session(tmp_path, {"state": "running", "pid": os.getpid(), "binaryPath": "/opt/none/nfqws2-not-this"})
    assert runtime_record_activity(path) is None
    path = _session(tmp_path, {"state": "running", "pid": os.getpid()})
    assert "live pid" in runtime_record_activity(path)


def test_socks_auth_secret_is_not_a_runtime_record(tmp_path: Path) -> None:
    path = tmp_path / ".zap2/tunnel/runtime/default.session-socks-auth.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"user": "u", "pass": "p"}))
    assert active_runtime_records(tmp_path) == {}


def test_block_message_names_records_and_escape_hatch(tmp_path: Path) -> None:
    old, new = _tiny(tmp_path, "old", "1.2.0"), _tiny(tmp_path, "new", "1.3.0")
    ws = tmp_path / "data/workspace"
    ensure_workspace(old, ws)
    _session(ws, {"state": "applied"}, "default.owner-rules.json")
    with pytest.raises(ValueError) as error:
        ensure_workspace(new, ws)
    text = str(error.value)
    assert "reconcile" in text and "default.owner-rules.json" in text and "--lifecycle-confirm-stopped" in text


def test_confirm_stopped_moves_records_without_deleting(tmp_path: Path) -> None:
    old, new = _tiny(tmp_path, "old", "1.2.0"), _tiny(tmp_path, "new", "1.3.0")
    ws = tmp_path / "data/workspace"
    ensure_workspace(old, ws)
    _session(ws, {"state": "applied", "secret": "keep"}, "default.owner-rules.json")
    moved = confirm_runtime_stopped(ws)
    assert len(moved) == 1 and json.loads(Path(moved[0]).read_text())["secret"] == "keep"
    assert ws not in Path(moved[0]).parents
    assert ensure_workspace(new, ws)["version"] == "1.3.0"


def test_confirm_stopped_refuses_live_process(tmp_path: Path) -> None:
    _session(tmp_path, {"state": "running", "pid": os.getpid()})
    with pytest.raises(ValueError, match="still alive"):
        confirm_runtime_stopped(tmp_path)
    assert (tmp_path / ".zap2/runtime/sessions/default.session.json").exists()


def test_boot_time_is_read_from_proc_stat() -> None:
    boot = distribution._boot_time()
    if Path("/proc/stat").exists():
        assert boot is not None and boot < time.time()
