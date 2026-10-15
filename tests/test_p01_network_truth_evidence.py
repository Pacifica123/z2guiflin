from __future__ import annotations

import json
import socket
import stat

import pytest
from pathlib import Path

import zap2_gui.adapters.discord_tunnel as tunnel
from zap2_gui.adapters.runtime_state import confirm_runtime_plan
from zap2_gui.models.network_evidence import (
    EvidenceGraph,
    FAIL,
    PASS,
    ProbeSpan,
    SUPPORT_UNKNOWN,
    SUPPORTED,
    UNSUPPORTED,
    aggregate_capability_verdicts,
    capability_from_required_spans,
)

SAMPLE_UUID = "11111111-2222-4333-8444-555555555555"
SAMPLE_VLESS = (
    f"vless://{SAMPLE_UUID}@example.net:8080"
    "?security=&encryption=none&host=www.example.org&headerType=http&type=tcp#P01"
)
UNKNOWN_KEY_VLESS = SAMPLE_VLESS.replace("#P01", "&futureKnob=opaque#P01")

FAKE_SOCKS_CORE = r'''#!/usr/bin/env python3
import json, socket, sys, time
from pathlib import Path
config = None
for index, arg in enumerate(sys.argv):
    if arg in {"-config", "-c"} and index + 1 < len(sys.argv):
        config = Path(sys.argv[index + 1]); break
if "-test" in sys.argv:
    raise SystemExit(0)
if "version" in sys.argv:
    print("Xray fake-p01")
    raise SystemExit(0)
port = int(json.loads(config.read_text(encoding="utf-8"))["inbounds"][0]["port"])
def _socks_settings():
    try:
        return json.loads(config.read_text(encoding="utf-8"))["inbounds"][0].get("settings", {})
    except Exception:
        return {}
SOCKS_SETTINGS = _socks_settings()
def handle(conn):
    # RFC1928/RFC1929 fake: honour the generated inbound auth mode.
    head = conn.recv(2)
    if len(head) < 2 or head[0] != 5:
        return
    methods = conn.recv(head[1])
    if SOCKS_SETTINGS.get("auth") == "password":
        if 2 not in methods:
            conn.sendall(b"\x05\xff"); return
        conn.sendall(b"\x05\x02")
        ver_len = conn.recv(2); user = conn.recv(ver_len[1]); plen = conn.recv(1)[0]; pw = conn.recv(plen)
        ok = any(a.get("user") == user.decode() and a.get("pass") == pw.decode() for a in SOCKS_SETTINGS.get("accounts", []))
        conn.sendall(b"\x01\x00" if ok else b"\x01\x01")
        if not ok:
            return
    else:
        if 0 not in methods:
            conn.sendall(b"\x05\xff"); return
        conn.sendall(b"\x05\x00")
    try:
        conn.recv(4096)
    except OSError:
        pass
server = socket.socket(); server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server.bind(("127.0.0.1", port)); server.listen(16); server.settimeout(0.2)
started=time.time()
while time.time()-started < 30:
    try: conn,_=server.accept()
    except socket.timeout: continue
    with conn:
        try:
            handle(conn)
        except Exception:
            pass
'''


def _executable(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def _unused_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])
    finally:
        sock.close()


def _span(run_id: str, kind: str, result: str, target: str = "") -> ProbeSpan:
    return ProbeSpan(span_id=f"{run_id}:{kind}:{target or 'local'}", kind=kind, run_id=run_id, result=result, target=target)


def test_connection_receipt_is_hash_bound_redacted_and_preserves_unknown_key_names(tmp_path: Path) -> None:
    tunnel.tunnel_connection_import_vless_to_text(UNKNOWN_KEY_VLESS, root=tmp_path)
    receipts = list((tmp_path / ".zap2" / "tunnel" / "receipts").glob("*.json"))
    assert len(receipts) == 1
    payload = json.loads(receipts[0].read_text(encoding="utf-8"))
    serialized = receipts[0].read_text(encoding="utf-8")

    assert payload["schemaVersion"] == 2
    assert payload["source"]["sourceHash"]
    assert payload["normalizedHash"]
    assert payload["rawUriStored"] is False
    assert "futureKnob" in payload["unknownQueryKeys"]
    assert SAMPLE_UUID not in serialized
    assert "vless://" not in serialized
    assert "example.net" not in serialized


def test_unknown_import_semantics_never_claim_full_supported_generation(tmp_path: Path) -> None:
    tunnel.tunnel_connection_import_vless_to_text(UNKNOWN_KEY_VLESS, root=tmp_path)
    fake_core = _executable(tmp_path / "xray", FAKE_SOCKS_CORE)
    text = tunnel.discord_tunnel_plan_to_text(root=tmp_path, core_binary=str(fake_core), socks_port=_unused_port())
    receipt = json.loads(next((tmp_path / ".zap2" / "tunnel" / "receipts").glob("*.json")).read_text(encoding="utf-8"))

    assert "generation support: EXPERIMENTAL" in text
    assert receipt["generation"]["support"] == "EXPERIMENTAL"
    assert receipt["generation"]["semanticFidelity"] == "partial"
    assert "futureKnob" in receipt["generation"]["unclassifiedQueryKeys"]


def test_current_run_tls_failure_beats_local_pass_and_stale_success() -> None:
    old_run = "run-old"
    run_id = "run-current"
    target = "updates.discord.com"
    spans = [
        _span(old_run, "process", PASS),
        _span(old_run, "listener", PASS),
        _span(old_run, "socks_method", PASS),
        _span(old_run, "socks_connect", PASS, target),
        _span(old_run, "target_tls", PASS, target),
        _span(old_run, "target_http", PASS, target),
        _span(run_id, "process", PASS),
        _span(run_id, "listener", PASS),
        _span(run_id, "socks_method", PASS),
        _span(run_id, "socks_connect", PASS, target),
        _span(run_id, "target_tls", FAIL, target),
    ]
    verdict = capability_from_required_spans(
        capability_id=f"route.https:{target}",
        run_id=run_id,
        spans=spans,
        requirements=(("process", None), ("listener", None), ("socks_method", None), ("socks_connect", target), ("target_tls", target), ("target_http", target)),
    )

    assert verdict.support == UNSUPPORTED
    assert f"target_tls@{target}" in verdict.failed_requirements
    assert verdict.stale_evidence_ignored
    assert all(ref.startswith(old_run) for ref in verdict.stale_evidence_ignored)


def test_vesktop_aggregate_requires_every_mandatory_subcapability() -> None:
    run_id = "run-vesktop"
    graph = EvidenceGraph(
        run_id=run_id,
        profile_id="default",
        connection_id="c1",
        connection_receipt_id="r1",
        core_identity_hash="core",
        config_hash="cfg",
    )
    for kind in ("process", "listener", "socks_method"):
        graph.add_span(_span(run_id, kind, PASS))
    for host in tunnel.VESKTOP_MANDATORY_HTTP_TARGETS:
        graph.add_span(_span(run_id, "socks_connect", PASS, host))
        graph.add_span(_span(run_id, "target_tls", PASS, host))
        graph.add_span(_span(run_id, "target_http", PASS, host))
    tunnel._refresh_capability_verdicts(graph)
    by_id = {item.capability_id: item for item in graph.verdicts}

    assert by_id["route.https:updates.discord.com"].support == SUPPORTED
    assert by_id["route.https:discord.com"].support == SUPPORTED
    assert by_id["discord.bootstrap.gateway"].support == SUPPORT_UNKNOWN
    assert by_id["vesktop.navigation"].support == SUPPORT_UNKNOWN
    assert by_id["vesktop.bootstrap"].support == SUPPORT_UNKNOWN


def test_failed_preflight_bypass_does_not_green_capability(tmp_path: Path, monkeypatch) -> None:
    tunnel.tunnel_connection_import_vless_to_text(SAMPLE_VLESS, root=tmp_path)
    fake_core = _executable(tmp_path / "xray", FAKE_SOCKS_CORE)
    fake_client = _executable(tmp_path / "vesktop", "#!/bin/sh\nsleep 30\n")
    port = _unused_port()
    tunnel.discord_tunnel_plan_to_text(root=tmp_path, core_binary=str(fake_core), socks_port=port)
    plan_id = "runtime-default-discord-tunnel-socks-start-plan"
    confirm_runtime_plan(root=tmp_path, plan_id=plan_id)
    start = tunnel.discord_tunnel_start_to_text(root=tmp_path, confirm_plan_id=plan_id)
    assert "Discord tunnel start: started" in start

    def fake_https(*_args, **_kwargs):
        return {
            "ok": False,
            "portOpen": True,
            "socksMethodOk": True,
            "socksConnectOk": True,
            "targetTlsOk": False,
            "targetHttpOk": False,
            "stage": "target-tls",
            "message": "fixture TLS failure",
            "statusCode": None,
            "elapsedMs": 1,
        }

    monkeypatch.setattr(tunnel, "_https_head_through_socks", fake_https)
    try:
        launched = tunnel.discord_launch_through_socks_to_text(
            root=tmp_path,
            discord_binary=str(fake_client),
            launch_mode="socks-env-only",
            upstream_preflight=True,
            allow_failed_preflight=True,
        )
        assert "failed-preflight bypass changes capability verdict: no" in launched
        discord_session = json.loads((tmp_path / ".zap2" / "tunnel" / "runtime" / "default.discord-session.json").read_text(encoding="utf-8"))
        assert discord_session["upstreamPreflight"]["allowFailed"] is True
        assert discord_session["upstreamPreflight"]["bypassChangesVerdict"] is False
        assert discord_session["upstreamPreflight"]["routeCapability"] == UNSUPPORTED

        evidence_text = tunnel.discord_tunnel_evidence_to_text(root=tmp_path)
        assert "route updates.discord.com: UNSUPPORTED" in evidence_text
        assert "vesktop bootstrap capability: UNSUPPORTED" in evidence_text
    finally:
        tunnel.discord_stop_launched_to_text(root=tmp_path)
        tunnel.discord_tunnel_stop_to_text(root=tmp_path)


def test_socks_plan_records_containment_not_fake_auth(tmp_path: Path) -> None:
    tunnel.tunnel_connection_import_vless_to_text(SAMPLE_VLESS, root=tmp_path)
    fake_core = _executable(tmp_path / "xray", FAKE_SOCKS_CORE)
    tunnel.discord_tunnel_plan_to_text(root=tmp_path, core_binary=str(fake_core), socks_port=_unused_port())
    plan = json.loads((tmp_path / ".zap2" / "runtime" / "plans" / "runtime-default-discord-tunnel-socks-start-plan.json").read_text(encoding="utf-8"))

    assert plan["localSocks"]["host"] == "127.0.0.1"
    assert plan["localSocks"]["auth"] == "password"
    assert len(plan["localSocks"]["credentialFingerprint"]) == 16
    assert "pass" not in json.dumps(plan["localSocks"]).replace("password", "")
    assert plan["localSocks"]["udp"] is False
    assert plan["localSocks"]["randomPortIsAuthentication"] is False
    assert plan["safety"]["socksContainment"]["loopbackOnly"] is True



def test_duplicate_vless_query_keys_are_rejected_instead_of_silently_collapsed() -> None:
    uri = (
        f"vless://{SAMPLE_UUID}@example.net:443"
        "?encryption=none&type=ws&type=tcp&security=tls#dup"
    )
    with pytest.raises(ValueError, match="повторяющиеся query-параметры"):
        tunnel.parse_vless_uri(uri)


def test_supported_generation_requires_exact_semantic_roundtrip(tmp_path: Path) -> None:
    tunnel.tunnel_connection_import_vless_to_text(SAMPLE_VLESS, root=tmp_path)
    fake_core = _executable(tmp_path / "xray", FAKE_SOCKS_CORE)
    text = tunnel.discord_tunnel_plan_to_text(root=tmp_path, core_binary=str(fake_core), socks_port=_unused_port())
    receipt = json.loads(next((tmp_path / ".zap2" / "tunnel" / "receipts").glob("*.json")).read_text(encoding="utf-8"))
    generation = receipt["generation"]

    assert "generation support: SUPPORTED" in text
    assert generation["support"] == SUPPORTED
    assert generation["semanticFidelity"] == "full"
    assert generation["semanticDiff"]["equal"] is True
    assert generation["semanticDiff"]["mismatchFields"] == []
    assert generation["sourceSemanticHash"] == generation["generatedSemanticHash"]


def test_known_but_unrepresented_grpc_mode_is_semantic_loss(tmp_path: Path) -> None:
    uri = (
        f"vless://{SAMPLE_UUID}@example.net:443"
        "?encryption=none&security=tls&type=grpc&serviceName=svc&mode=gun#grpc"
    )
    tunnel.tunnel_connection_import_vless_to_text(uri, root=tmp_path)
    fake_core = _executable(tmp_path / "xray", FAKE_SOCKS_CORE)
    text = tunnel.discord_tunnel_plan_to_text(root=tmp_path, core_binary=str(fake_core), socks_port=_unused_port())
    receipt = json.loads(next((tmp_path / ".zap2" / "tunnel" / "receipts").glob("*.json")).read_text(encoding="utf-8"))

    assert "generation support: UNSUPPORTED" in text
    assert receipt["generation"]["support"] == UNSUPPORTED
    assert "query:mode-unsupported-value" in receipt["generation"]["requiredLoss"]


def test_connection_receipt_redacts_owner_path_and_transport_path(tmp_path: Path) -> None:
    uri = (
        f"vless://{SAMPLE_UUID}@example.net:443"
        "?encryption=none&security=tls&type=ws&path=%2Fprivate-route-token&host=edge.example.org#PersonalLabel"
    )
    source_file = tmp_path / "private" / "owner-profile.txt"
    source_file.parent.mkdir(parents=True)
    source_file.write_text(uri, encoding="utf-8")
    tunnel.tunnel_connection_import_vless_to_text(f"@{source_file}", root=tmp_path)
    receipt_path = next((tmp_path / ".zap2" / "tunnel" / "receipts").glob("*.json"))
    payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    serialized = receipt_path.read_text(encoding="utf-8")

    assert payload["source"]["kind"] == "file"
    assert str(source_file) not in serialized
    assert "/private-route-token" not in serialized
    assert "PersonalLabel" not in serialized
    assert payload["connection"]["path"]["present"] is True
    assert payload["connection"]["remarks"]["present"] is True


def test_probe_span_failure_class_is_typed_and_serialized() -> None:
    eof = tunnel._probe_span(
        run_id="run-eof",
        kind="target_tls",
        result=FAIL,
        target="updates.discord.com",
        detail={"stage": "target-tls", "message": "unexpected EOF while reading"},
    )
    timeout = tunnel._probe_span(
        run_id="run-timeout",
        kind="target_tls",
        result=FAIL,
        target="updates.discord.com",
        detail={"stage": "target-tls", "message": "handshake timed out"},
    )

    assert eof.failure_class == "target_tls_eof_or_reset"
    assert timeout.failure_class == "target_tls_timeout"
    assert eof.to_dict()["failureClass"] == "target_tls_eof_or_reset"


def test_bound_graph_rejects_config_receipt_or_core_identity_mismatch(tmp_path: Path) -> None:
    paths = tunnel.ensure_tunnel_store(tmp_path)
    graph = EvidenceGraph(
        run_id="run-bind",
        profile_id="default",
        connection_id="c1",
        connection_receipt_id="receipt-1",
        core_identity_hash="core-1",
        config_hash="cfg-1",
    )
    tunnel._write_evidence_graph(paths, graph)
    session = {
        "runId": "run-bind",
        "connectionId": "c1",
        "connectionReceiptId": "receipt-1",
        "configHash": "cfg-OTHER",
        "coreCapability": {"identityHash": "core-1"},
    }

    with pytest.raises(ValueError, match="EvidenceGraph binding mismatch"):
        tunnel._load_bound_evidence_graph(paths, "default", session)


def test_neutral_control_target_gets_its_own_route_verdict(tmp_path: Path) -> None:
    paths = tunnel.ensure_tunnel_store(tmp_path)
    run_id = "run-neutral"
    graph = EvidenceGraph(
        run_id=run_id,
        profile_id="default",
        connection_id="c1",
        connection_receipt_id="receipt-1",
        core_identity_hash="core-1",
        config_hash="cfg-1",
    )
    for kind in ("process", "listener", "socks_method"):
        graph.add_span(_span(run_id, kind, PASS))
    tunnel._write_evidence_graph(paths, graph)
    session = {
        "runId": run_id,
        "connectionId": "c1",
        "connectionReceiptId": "receipt-1",
        "configHash": "cfg-1",
        "coreCapability": {"identityHash": "core-1"},
    }
    result = {
        "ok": True,
        "stage": "target-http",
        "socksMethodOk": True,
        "socksConnectOk": True,
        "targetTlsOk": True,
        "targetHttpOk": True,
        "statusCode": 204,
        "statusLine": "HTTP/1.1 204 No Content",
        "message": "fixture pass",
    }

    _path, support = tunnel._record_https_probe_evidence(
        paths,
        "default",
        session,
        target_host="example.com",
        target_path="/",
        result=result,
        producer="test-neutral",
    )
    loaded = tunnel._load_bound_evidence_graph(paths, "default", session)
    neutral = next(item for item in loaded.verdicts if item.capability_id == "route.https:example.com")

    assert support == SUPPORTED
    assert neutral.support == SUPPORTED
    assert next(item for item in loaded.verdicts if item.capability_id == "vesktop.bootstrap").support == SUPPORT_UNKNOWN
