#!/usr/bin/env python3
"""Dependency-free regression check for runtime/VLESS/Vesktop recovery patch.

This is intentionally stdlib-only so devctl can validate the patch on a clean
Arch/EndeavourOS host where pytest is not installed system-wide.
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import stat
import subprocess
import tempfile
from pathlib import Path

from zap2_gui.adapters.discord_tunnel import (
    _discord_launch_argv,
    discord_tunnel_plan_to_text,
    discord_tunnel_start_to_text,
    discord_tunnel_stop_to_text,
    generate_xray_vless_socks_config,
    parse_vless_uri,
    tunnel_connection_import_vless_to_text,
)
from zap2_gui.adapters.runtime_apply import (
    RuntimeCommandResult,
    create_runtime_apply_plan,
    execute_runtime_owner_rules,
    prepare_runtime_owner_rules_plan,
)
from zap2_gui.adapters.runtime_session import SESSION_MARKER, runtime_session_status, stop_runtime_session
from zap2_gui.adapters.runtime_state import confirm_runtime_plan

SAMPLE_VLESS = (
    "vless://11111111-2222-4333-8444-555555555555@example.net:8080"
    "?security=&encryption=none&host=www.example.org&headerType=http&type=tcp#Smoke"
)
REALITY_VLESS = (
    "vless://11111111-2222-4333-8444-555555555555@203.0.113.10:8443"
    "?security=reality&encryption=none&type=tcp&flow=xtls-rprx-vision"
    "&sni=storage.example.net&fp=firefox&pbk=PUBLICKEY123&sid=0905b6e16602f326&spx=%2F#Reality"
)
FAKE_SOCKS_CORE = r'''#!/usr/bin/env python3
import json, socket, sys, time
from pathlib import Path
config = None
for index, arg in enumerate(sys.argv):
    if arg in {"-config", "-c"} and index + 1 < len(sys.argv):
        config = Path(sys.argv[index + 1]); break
if "-test" in sys.argv:
    raise SystemExit(0)
if config is None:
    raise SystemExit(2)
port = int(json.loads(config.read_text(encoding="utf-8"))["inbounds"][0]["port"])
server = socket.socket(); server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server.bind(("127.0.0.1", port)); server.listen(8); server.settimeout(0.2)
started = time.time()
while time.time() - started < 30:
    try: conn, _ = server.accept()
    except socket.timeout: continue
    with conn:
        if conn.recv(3) == b"\x05\x01\x00": conn.sendall(b"\x05\x00")
'''
FAKE_NO_SOCKS_CORE = "#!/bin/sh\nsleep 30\n"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def executable(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def check_vless_schema() -> None:
    profile = parse_vless_uri(SAMPLE_VLESS)
    xray = generate_xray_vless_socks_config(profile, socks_port=free_port(), core_kind="xray")
    out = xray["outbounds"][0]
    require(out["settings"]["address"] == "example.net", "Xray simplified VLESS address missing")
    require(out["settings"]["id"] == profile.user_id, "Xray simplified VLESS id missing")
    require("vnext" not in out["settings"], "Xray unexpectedly uses classic vnext schema")
    require(out["streamSettings"]["method"] == "raw", "Xray raw transport mapping missing")
    require("rawSettings" in out["streamSettings"], "Xray rawSettings missing")

    v2ray = generate_xray_vless_socks_config(profile, socks_port=free_port(), core_kind="v2ray")
    out2 = v2ray["outbounds"][0]
    require(out2["settings"]["vnext"][0]["address"] == "example.net", "V2Ray classic vnext schema missing")
    require(out2["streamSettings"]["network"] == "tcp", "V2Ray tcp network missing")

    reality = generate_xray_vless_socks_config(parse_vless_uri(REALITY_VLESS), socks_port=free_port(), core_kind="xray")
    rs = reality["outbounds"][0]["streamSettings"]["realitySettings"]
    require(rs.get("password") == "PUBLICKEY123", "Xray REALITY password field missing")
    require("publicKey" not in rs, "Xray REALITY still emits legacy publicKey")


def check_tunnel_readiness() -> None:
    with tempfile.TemporaryDirectory(prefix="zap2-vless-smoke-") as td:
        root = Path(td)
        tunnel_connection_import_vless_to_text(SAMPLE_VLESS, root=root)
        core = executable(root / "xray", FAKE_SOCKS_CORE)
        port = free_port()
        discord_tunnel_plan_to_text(root=root, core_binary=str(core), socks_port=port)
        plan_id = "runtime-default-discord-tunnel-socks-start-plan"
        confirm_runtime_plan(root=root, plan_id=plan_id)
        started = discord_tunnel_start_to_text(
            root=root,
            confirm_plan_id=plan_id,
            allow_parallel_with_zapret=True,
        )
        require("Discord tunnel start: started" in started, "SOCKS-capable fake core did not start")
        session = json.loads((root / ".zap2/tunnel/runtime/default.session.json").read_text(encoding="utf-8"))
        require(session.get("socksReady") is True, "successful start did not persist socksReady=true")
        stopped = discord_tunnel_stop_to_text(root=root)
        require("Discord tunnel stop: stopped" in stopped, "managed fake core did not stop")

    with tempfile.TemporaryDirectory(prefix="zap2-vless-failclosed-") as td:
        root = Path(td)
        tunnel_connection_import_vless_to_text(SAMPLE_VLESS, root=root)
        core = executable(root / "xray", FAKE_NO_SOCKS_CORE)
        port = free_port()
        discord_tunnel_plan_to_text(root=root, core_binary=str(core), socks_port=port)
        plan_id = "runtime-default-discord-tunnel-socks-start-plan"
        confirm_runtime_plan(root=root, plan_id=plan_id)
        failed = discord_tunnel_start_to_text(
            root=root,
            confirm_plan_id=plan_id,
            allow_parallel_with_zapret=True,
        )
        require("Discord tunnel start: failed" in failed, "alive core without SOCKS was falsely accepted")
        session = json.loads((root / ".zap2/tunnel/runtime/default.session.json").read_text(encoding="utf-8"))
        require(session.get("state") == "failed", "failed core session state not persisted")
        require(session.get("socksReady") is False, "failed core unexpectedly marked socksReady")


def check_vesktop_launch_composer() -> None:
    with tempfile.TemporaryDirectory(prefix="zap2-vesktop-smoke-") as td:
        root = Path(td)
        vesktop = executable(root / "vesktop", "#!/bin/sh\nexit 0\n")
        argv, raw = _discord_launch_argv(str(vesktop), "127.0.0.1", 19080, "socks-updater-window")
        require(raw == str(vesktop), "explicit Vesktop command changed unexpectedly")
        require("--proxy-server=socks5://127.0.0.1:19080" in argv, "Vesktop proxy-server flag missing")
        require("--disable-quic" in argv, "Vesktop disable-quic flag missing")

    project_root = Path(__file__).resolve().parents[1]
    app_source = (project_root / "gui/zap2_gui/app.py").read_text(encoding="utf-8")
    widget_source = (project_root / "gui/zap2_gui/widgets/tunnel.py").read_text(encoding="utf-8")
    combined = app_source + "\n" + widget_source
    require("Vesktop" in combined, "GUI/CLI sources do not expose Vesktop")


def check_legacy_session_adoption() -> None:
    with tempfile.TemporaryDirectory(prefix="zap2-runtime-session-") as td:
        root = Path(td)
        binary = root / "legacy-sleep"
        shutil.copyfile("/bin/sleep", binary)
        binary.chmod(0o755)
        sessions = root / ".zap2/runtime/sessions"
        sessions.mkdir(parents=True, exist_ok=True)
        pidfile = sessions / "default.pid"
        session_path = sessions / "default.session.json"
        proc = subprocess.Popen([str(binary), "30"])
        try:
            pidfile.write_text(str(proc.pid), encoding="utf-8")
            session_path.write_text(json.dumps({
                "schemaVersion": 1,
                "marker": SESSION_MARKER,
                "state": "running",
                "profileId": "default",
                "rootPath": str(root),
                "sessionPath": str(session_path),
                "pid": proc.pid,
                "binaryPath": str(binary),
                "argv": [str(binary), "30"],
                "pidfilePath": str(pidfile),
                "planId": "legacy-plan",
                "planHash": "legacy-hash",
            }), encoding="utf-8")
            status = runtime_session_status(root, "default")
            require(status.state == "running", "valid schema-1 session was not adopted")
            upgraded = json.loads(session_path.read_text(encoding="utf-8"))
            require(upgraded.get("schemaVersion") == 2, "schema-1 session was not upgraded to schema 2")
            require(bool(upgraded.get("processIdentity", {}).get("procStartTime")), "upgraded session lacks process identity")
            stopped = stop_runtime_session(root, "default")
            require(stopped.state == "stopped", "adopted legacy runtime could not be stopped")
        finally:
            if proc.poll() is None:
                proc.terminate()
                proc.wait(timeout=5)


def check_legacy_nft_migration() -> None:
    with tempfile.TemporaryDirectory(prefix="zap2-runtime-nft-") as td:
        source_root = Path(__file__).resolve().parents[1]
        root = Path(td) / "project"
        shutil.copytree(
            source_root,
            root,
            ignore=shutil.ignore_patterns(".git", ".zap2", "__pycache__", ".pytest_cache", "*.pyc", "*.zip"),
        )
        prepared = prepare_runtime_owner_rules_plan(root, action="apply", profile_id="default")
        confirm_runtime_plan(root, prepared.plan_id)
        expected = create_runtime_apply_plan(root, action="apply", profile_id="default")
        state_path = root / ".zap2/runtime/sessions/default.owner-rules.json"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps({
            "schemaVersion": 1,
            "marker": "zap2-runtime-apply-v1",
            "state": "applied",
            "profileId": "default",
            "nftTable": "zap2_default",
            "ownerUid": expected.owner_uid,
        }), encoding="utf-8")

        def runner(argv: tuple[str, ...]) -> RuntimeCommandResult:
            if argv[:4] == ("nft", "list", "table", "inet"):
                if argv[4] == "zap2_default":
                    return RuntimeCommandResult(argv, 0, stdout="table inet zap2_default { chain local_out { } }")
                return RuntimeCommandResult(argv, 1, stderr="No such table")
            return RuntimeCommandResult(argv, 0)

        result = execute_runtime_owner_rules(
            root,
            action="apply",
            profile_id="default",
            confirm_plan_id=prepared.plan_id,
            runner=runner,
            allow_without_root=True,
        )
        require(result.state == "applied", "proven legacy nft table migration did not apply")
        state = json.loads(result.state_path.read_text(encoding="utf-8"))
        require(state.get("legacyNftTableMigrated") == "zap2_default", "legacy nft migration not recorded")
        transaction = (root / state["transactionPath"]).read_text(encoding="utf-8")
        require(transaction.splitlines()[0] == "delete table inet zap2_default", "legacy table deletion is not first in checked transaction")
        require(f"add table inet {expected.nft_table}" in transaction, "new owner-specific table missing from migration transaction")


def main() -> int:
    checks = [
        ("VLESS Xray/V2Ray schema", check_vless_schema),
        ("Tunnel SOCKS readiness/fail-closed", check_tunnel_readiness),
        ("Vesktop proxy launch composition", check_vesktop_launch_composer),
        ("Legacy runtime session adoption", check_legacy_session_adoption),
        ("Legacy nft table migration", check_legacy_nft_migration),
    ]
    for label, func in checks:
        func()
        print(f"[PASS] {label}")
    print(f"[PASS] dependency-free runtime/VLESS/Vesktop smoke suite ({len(checks)} checks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
