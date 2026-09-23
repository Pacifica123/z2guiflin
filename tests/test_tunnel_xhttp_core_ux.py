from __future__ import annotations

import stat
from pathlib import Path

from zap2_gui.adapters.discord_tunnel import (
    discord_launch_through_socks_to_text,
    discord_tunnel_plan_to_text,
    discord_tunnel_probe_to_text,
    discord_tunnel_start_to_text,
    discord_tunnel_status_to_text,
    tunnel_connection_import_vless_to_text,
)
from zap2_gui.adapters.runtime_state import confirm_runtime_plan


XHTTP_VLESS = (
    "vless://11111111-2222-4333-8444-555555555555@203.0.113.10:80"
    "?security=none&encryption=none&type=xhttp&host=cdn.example.net&path=%2F&mode=auto#XHTTP"
)


def _executable(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def test_plan_warns_for_xhttp_with_v2ray_core(tmp_path: Path) -> None:
    tunnel_connection_import_vless_to_text(XHTTP_VLESS, root=tmp_path)
    fake_v2ray = _executable(tmp_path / "v2ray", "#!/bin/sh\nsleep 30\n")

    text = discord_tunnel_plan_to_text(root=tmp_path, core_binary=str(fake_v2ray), core_kind="v2ray")

    assert "compatibility warning:" in text
    assert "transport xhttp" in text
    assert "V2Ray core" in text


def test_start_blocks_xhttp_with_v2ray_before_writing_failed_session(tmp_path: Path) -> None:
    tunnel_connection_import_vless_to_text(XHTTP_VLESS, root=tmp_path)
    fake_v2ray = _executable(tmp_path / "v2ray", "#!/bin/sh\nexit 1\n")

    discord_tunnel_plan_to_text(root=tmp_path, core_binary=str(fake_v2ray), core_kind="v2ray")
    plan_id = "runtime-default-discord-tunnel-socks-start-plan"
    confirm_runtime_plan(root=tmp_path, plan_id=plan_id)

    text = discord_tunnel_start_to_text(root=tmp_path, confirm_plan_id=plan_id)

    assert "Discord tunnel start: blocked" in text
    assert "compatibility issue:" in text
    assert "transport xhttp" in text
    assert "executes core now: no" in text
    assert not (tmp_path / ".zap2" / "tunnel" / "runtime" / "default.session.json").exists()


def test_failed_session_reports_core_stderr_and_better_launch_next_step(tmp_path: Path) -> None:
    tunnel_root = tmp_path / ".zap2" / "tunnel"
    runtime = tunnel_root / "runtime"
    logs = tunnel_root / "logs"
    runtime.mkdir(parents=True)
    logs.mkdir(parents=True)
    (runtime / "default.session.json").write_text(
        '{"state":"failed","pid":45949,"socksHost":"127.0.0.1","socksPort":10808}',
        encoding="utf-8",
    )
    (logs / "default.core.stderr.log").write_text(
        "Failed to start: main/commands: failed to load config: [default.core.json] > infra/conf/v4: Config: unknown transport protocol: xhttp\n",
        encoding="utf-8",
    )

    probe = discord_tunnel_probe_to_text(root=tmp_path)
    assert "verdict: T0_CORE_FAILED" in probe
    assert "unknown transport protocol: xhttp" in probe
    assert "core failure details:" in probe

    status = discord_tunnel_status_to_text(root=tmp_path)
    assert "core failure details:" in status
    assert "unknown transport protocol: xhttp" in status

    try:
        discord_launch_through_socks_to_text(root=tmp_path)
    except ValueError as exc:
        message = str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected failed tunnel session to block Discord launch")

    assert "Tunnel core не running" in message
    assert "session state=failed" in message
    assert "unknown transport protocol: xhttp" in message
    assert "исправьте core/profile compatibility" in message
