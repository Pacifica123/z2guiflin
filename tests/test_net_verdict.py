"""Сетевой вердикт: парсеры и классификатор на фикстурах, без реальной сети."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from zap2_gui.adapters import net_verdict as nv

ROOT = Path(__file__).resolve().parents[1]


def _ping_text(rtts: dict[int, float], count: int, dup: tuple[int, ...] = (), summary: bool = True) -> str:
    lines = [f"PING 192.168.1.1 (192.168.1.1) 56(84) bytes of data."]
    for seq in range(1, count + 1):
        if seq in rtts:
            lines.append(f"64 bytes from 192.168.1.1: icmp_seq={seq} ttl=64 time={rtts[seq]} ms")
            if seq in dup:
                lines.append(f"64 bytes from 192.168.1.1: icmp_seq={seq} ttl=64 time={rtts[seq]} ms (DUP!)")
    if summary:
        received = len(rtts)
        loss = round(100 * (count - received) / count)
        lines.append("--- 192.168.1.1 ping statistics ---")
        extra = f", +{len(dup)} duplicates" if dup else ""
        lines.append(f"{count} packets transmitted, {received} received{extra}, {loss}% packet loss, time 9000ms")
        if rtts:
            vals = list(rtts.values())
            lines.append(f"rtt min/avg/max/mdev = {min(vals)}/{sum(vals) / len(vals):.3f}/{max(vals)}/2.000 ms")
    return "\n".join(lines) + "\n"


def stats(target, loss=0.0, avg=10.0, mdev=1.0, run=0, jumps=0, label=""):
    return nv.PingStats(target=target, label=label, transmitted=30, received=30, loss_pct=loss,
                        rtt_min=avg, rtt_avg=avg, rtt_max=avg, rtt_mdev=mdev, longest_loss_run=run, jump_count=jumps)


def curl(rc=0, code=200, connect=0.02, app=0.05):
    return nv.CurlMetrics(rc=rc, http_code=code, time_connect=connect, time_appconnect=app)


def probe(host, role, outcome, tcp_ok=True):
    return nv.TargetProbe(host=host, role=role, addresses=["93.184.215.14"], tcp_ok=tcp_ok, outcome=outcome)


def healthy(**over) -> nv.Measurements:
    m = nv.Measurements(route_v4=True, route_v6=False, gateway="192.168.1.1",
                        gateway_ping=stats("192.168.1.1", avg=2, mdev=0.5),
                        external_pings=[stats("1.1.1.1", avg=20), stats("8.8.8.8", avg=25)],
                        dns=[nv.DnsCheck("example.com", ["93.184.215.14"]), nv.DnsCheck("archlinux.org", ["95.217.163.246"])],
                        probes=[probe("example.com", "control", nv.PROBE_OK), probe("www.youtube.com", "blocked", nv.PROBE_OK)],
                        zapret_status="not-started")
    for key, value in over.items():
        setattr(m, key, value)
    return m


# ---------------------------------------------------------------- parsers
def test_parse_ping_clean():
    s = nv.parse_ping(_ping_text({i: 10.0 for i in range(1, 11)}, 10), "gw", count=10)
    assert s.loss_pct == 0 and s.received == 10 and s.duplicates == 0
    assert s.rtt_avg == pytest.approx(10.0) and s.longest_loss_run == 0 and s.jump_count == 0


def test_parse_ping_gaps_jumps_and_dup():
    rtts = {1: 5.0, 2: 6.0, 3: 50.0, 7: 5.0, 8: 5.0}
    s = nv.parse_ping(_ping_text(rtts, 10, dup=(2,)), "gw", count=10, jump_ms=30)
    assert s.duplicates == 1
    assert s.loss_pct == 50
    assert s.longest_loss_run == 3          # 4,5,6
    assert s.max_jump_ms == pytest.approx(44.0)
    assert s.jump_count == 1                # 3->7 не соседние
    # tail: 9, 10 потеряны -> 2 < 3


def test_parse_ping_tail_loss_and_first_missing():
    s = nv.parse_ping(_ping_text({5: 1.0, 6: 1.0}, 10), "gw", count=10)
    assert s.longest_loss_run == 4


def test_parse_ping_no_reply():
    text = "PING 10.0.0.1 56(84) bytes of data.\n\n--- 10.0.0.1 ping statistics ---\n5 packets transmitted, 0 received, 100% packet loss, time 4000ms\n"
    s = nv.parse_ping(text, "10.0.0.1", count=5)
    assert s.loss_pct == 100 and s.rtt_avg is None and s.longest_loss_run == 5


def test_parse_ping_garbage():
    s = nv.parse_ping("ping: connect: Network is unreachable\n", "1.1.1.1", count=5)
    assert not s.has_summary and s.error


def test_parse_curl_metrics_and_phases():
    ok = nv.parse_curl_metrics("200 0.004 0.030 0.080 0.150 93.184.215.14\n", 0)
    assert ok.http_code == 200 and ok.time_appconnect == pytest.approx(0.08) and ok.remote_ip == "93.184.215.14"
    assert nv.classify_https_probe(ok, True, True) == nv.PROBE_OK
    tls_timeout = nv.parse_curl_metrics("000 0.003 0.031 0.000 0.000", 28)
    assert nv.classify_https_probe(tls_timeout, True, True) == nv.PROBE_TLS_FAIL
    rst = nv.parse_curl_metrics("000 0.003 0.031 0.000 0.000", 35)
    assert nv.classify_https_probe(rst, True, True) == nv.PROBE_TLS_FAIL
    tcp = nv.parse_curl_metrics("000 0.003 0.000 0.000 0.000", 28)
    assert nv.classify_https_probe(tcp, False, True) == nv.PROBE_TCP_FAIL
    after_tls = nv.parse_curl_metrics("000 0.003 0.03 0.09 0.000", 56)
    assert nv.classify_https_probe(after_tls, True, True) == nv.PROBE_HTTP_FAIL
    assert nv.classify_https_probe(None, None, False) == nv.PROBE_DNS_FAIL
    assert nv.parse_curl_metrics("", 6).http_code == 0


def test_is_bogon():
    assert nv.is_bogon("10.10.34.35") and nv.is_bogon("127.0.0.1") and not nv.is_bogon("1.1.1.1")


# ---------------------------------------------------------------- classifier
def test_verdict_ok():
    v = nv.classify(healthy())
    assert v.code == nv.VERDICT_OK and v.confidence == "high"
    assert any("гипотеза" in n.lower() for n in v.notes)


def test_verdict_no_route():
    v = nv.classify(healthy(route_v4=False, route_v6=False))
    assert v.code == nv.VERDICT_LOCAL_NO_ROUTE and v.confidence == "high"


def test_verdict_local_link():
    v = nv.classify(healthy(gateway_ping=stats("192.168.1.1", loss=10, mdev=25, run=4)))
    assert v.code == nv.VERDICT_LOCAL_LINK and v.next_steps and v.evidence


def test_verdict_isp_uplink():
    v = nv.classify(healthy(external_pings=[stats("1.1.1.1", loss=20), stats("8.8.8.8", avg=400)]))
    assert v.code == nv.VERDICT_ISP_UPLINK and v.confidence == "high"


def test_gateway_ignoring_icmp_is_not_local_fault():
    v = nv.classify(healthy(gateway_ping=stats("192.168.1.1", loss=100)))
    assert v.code == nv.VERDICT_OK


def test_verdict_dns_fail_and_bogon():
    v = nv.classify(healthy(dns=[nv.DnsCheck("example.com", [], error="Name or service not known"),
                                 nv.DnsCheck("archlinux.org", [])]))
    assert v.code == nv.VERDICT_DNS
    v = nv.classify(healthy(dns=[nv.DnsCheck("example.com", ["10.10.34.35"], public=["93.184.215.14"])]))
    assert v.code == nv.VERDICT_DNS and "bogon" in " ".join(v.evidence)


def test_verdict_dpi_selective_vs_ip_block():
    v = nv.classify(healthy(probes=[probe("example.com", "control", nv.PROBE_OK),
                                    probe("www.youtube.com", "blocked", nv.PROBE_TLS_FAIL, tcp_ok=True)]))
    assert v.code == nv.VERDICT_DPI_SELECTIVE and v.confidence == "high"
    v = nv.classify(healthy(probes=[probe("example.com", "control", nv.PROBE_OK),
                                    probe("discord.com", "blocked", nv.PROBE_TCP_FAIL, tcp_ok=False)]))
    assert v.code == nv.VERDICT_IP_BLOCK


def test_verdict_inconclusive():
    assert nv.classify(nv.Measurements()).code == nv.VERDICT_INCONCLUSIVE
    v = nv.classify(healthy(probes=[probe("example.com", "control", nv.PROBE_TLS_FAIL)]))
    assert v.code == nv.VERDICT_INCONCLUSIVE and v.confidence == "low"


def test_zapret_running_recorded_and_lowers_ok_confidence():
    v = nv.classify(healthy(zapret_status="running"))
    assert v.confidence == "medium" and any("running" in n for n in v.notes)


def test_every_verdict_has_next_steps_and_title():
    for code in nv.NEXT_STEPS:
        assert nv.NEXT_STEPS[code] and code in nv.VERDICT_TITLES


def test_report_roundtrip(tmp_path):
    m = healthy()
    v = nv.classify(m)
    path = nv.save_report(m, v, tmp_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["verdict"]["code"] == "OK" and "disclaimer" in data
    assert "Что проверить дальше" in nv.verdict_to_text(m, v)


def test_default_blocked_targets_from_registry():
    targets = nv.default_blocked_targets()
    assert "youtube.com" in targets and any("discord" in t for t in targets)


def test_standalone_script_help(tmp_path):
    script = tmp_path / "net_verdict.py"
    shutil.copyfile(ROOT / "gui/zap2_gui/adapters/net_verdict.py", script)
    proc = subprocess.run([sys.executable, "-I", str(script), "--help"], capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0 and "--blocked" in proc.stdout


def test_gui_button_wiring_is_self_contained():
    lab = (ROOT / "gui/zap2_gui/widgets/blockcheck_lab.py").read_text(encoding="utf-8")
    assert "make_net_verdict_button(" in lab
    panel = (ROOT / "gui/zap2_gui/widgets/net_verdict_panel.py").read_text(encoding="utf-8")
    assert "QThread" in panel and "Диагностика сети (вердикт)" in panel
    assert "sudo" not in (ROOT / "gui/zap2_gui/adapters/net_verdict.py").read_text(encoding="utf-8").replace("Без sudo", "").replace("без sudo", "")
    assert "net_verdict" not in (ROOT / "gui/zap2_gui/app.py").read_text(encoding="utf-8")


def test_net_verdict_modules_are_in_shipping_allowlist() -> None:
    import json
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    files = set(json.loads((root / "packaging/release-files.json").read_text(encoding="utf-8"))["files"])
    # blockcheck_lab импортирует панель: без неё установленный GUI не запустится.
    for rel in ("gui/zap2_gui/adapters/net_verdict.py", "gui/zap2_gui/widgets/net_verdict_panel.py"):
        assert rel in files, rel
