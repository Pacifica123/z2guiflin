"""P2 unit + POSIX-pipe contract tests; never starts a real Chrome or network."""
from __future__ import annotations

import os
import stat
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "gui"))

from zap2_gui.adapters.googlevideo_cdp import (
    CdpHostCollector, capture_browser_googlevideo, googlevideo_host_from_url,
)
from zap2_gui.adapters.googlevideo_node import (
    GooglevideoCandidate, GooglevideoDiscovery, merge_browser_googlevideo_hosts,
)


def test_cdp_strict_hostname_extraction_never_returns_signed_url():
    url = "https://rr3---sn-h0jelne7.googlevideo.com/videoplayback?expire=123&sig=SECRET"
    assert googlevideo_host_from_url(url) == "rr3---sn-h0jelne7.googlevideo.com"
    for bad in (
        "https://rr3---sn-h0jelne7.googlevideo.com.evil.net/a",
        "https://evil.net/?url=rr3---sn-h0jelne7.googlevideo.com",
        "https://user:secret@rr3---sn-h0jelne7.googlevideo.com/",
        "https://rr3---sn-h0jelne7.googlevideo.com:9999/",
        "file:///etc/passwd",
        "https://redirector.googlevideo.com/report_mapping?di=no",
        "http://rr4---sn-h0jelne7.googlevideo.com.evil.com/",
        "https://rr3---sn-h0jelne7.googlevideo.com\\@evil.test/",
    ):
        assert not googlevideo_host_from_url(bad)


def test_collector_restricts_events_and_does_not_keep_url():
    collector = CdpHostCollector(max_hosts=2)
    private = "SECRET_TOKEN_NEVER_PERSIST"
    for i in range(4):
        collector.ingest({"method": "Network.requestWillBeSent", "params": {
            "requestId": str(i), "request": {"url": f"https://rr{i+1}---sn-h0jelne7.googlevideo.com/videoplayback?sig={private}"},
        }})
    collector.ingest({"method": "Runtime.consoleAPICalled", "params": {
        "args": [{"value": "https://rr9---sn-test.googlevideo.com"}],
    }})
    assert collector.hosts == ("rr1---sn-h0jelne7.googlevideo.com", "rr2---sn-h0jelne7.googlevideo.com")
    assert private not in repr(vars(collector))


def test_merge_browser_targets_preferred_and_fallback_kept():
    fallback = GooglevideoDiscovery((
        GooglevideoCandidate("rr1---sn-backup.googlevideo.com", "redirector", "unchecked"),
    ))
    result = merge_browser_googlevideo_hosts((
        "rr4---sn-live.googlevideo.com", "rr4---sn-live.googlevideo.com",
        "invalid.evil.example", "rr5---sn-live.googlevideo.com",
    ), fallback, dns_check=lambda h, t: h.startswith("rr4"))
    assert result.hosts == ("rr4---sn-live.googlevideo.com", "rr1---sn-backup.googlevideo.com")
    assert result.rejected_dns == ("rr5---sn-live.googlevideo.com",)
    assert result.candidates[0].source == "browser"
    assert "CDP" in result.to_text()
    assert merge_browser_googlevideo_hosts(("rr1---sn-test.googlevideo.com",), fallback, skip_dnscheck=True).hosts[0] == "rr1---sn-test.googlevideo.com"


FAKE_CHROME = r'''#!/usr/bin/env python3
import json, os, select, sys, time
assert '--remote-debugging-pipe' in sys.argv
profile=[a.split('=',1)[1] for a in sys.argv if a.startswith('--user-data-dir=')][0]
assert os.stat(profile).st_mode & 0o777 == 0o700
with open(sys.argv[0]+'.profile','w') as marker:marker.write(profile)
assert not any(a.startswith('--remote-debugging-port') for a in sys.argv)
responses=[]
while True:
    rd,_,_=select.select([3], [], [], 0.1)
    if not rd: continue
    data=os.read(3, 100000)
    if not data: break
    for msg in data.split(b'\x00'):
        if not msg: continue
        c=json.loads(msg)
        method=c['method']
        result={}
        if method=='Target.getTargets':
            result={'targetInfos':[{'type':'page','targetId':'a1','attached':False}]}
        if method=='Target.attachToTarget':
            result={'sessionId':'session1'}
        out={'id':c['id'],'result':result}
        os.write(4, json.dumps(out).encode()+b'\x00')
        if method=='Network.enable':
            events=[
                {'method':'Network.requestWillBeSent','params':{'requestId':'r1','request':{'url':'https://rr2---sn-h0jelne7.googlevideo.com/videoplayback?sig=LEAKED_SECRET'}}},
                {'method':'Network.responseReceived','params':{'requestId':'r2','response':{'url':'https://rr3---sn-h0jelne7.googlevideo.com/videoplayback?token=PRIVATE'}}},
                {'method':'Network.loadingFailed','params':{'requestId':'r1','errorText':'secret text should not escape'}}]
            for event in events:os.write(4,json.dumps(event).encode()+b'\x00')
            with open(sys.argv[0]+'.seen','w') as marker:marker.write('ready')
'''


def fake_chromium(tmp_path: Path) -> str:
    binary = tmp_path / "fake-chromium"
    binary.write_text(FAKE_CHROME)
    binary.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
    return str(binary)


def test_private_cdp_pipe_capture_and_profile_cleanup(tmp_path: Path):
    if os.name != "posix" or not hasattr(os, "posix_spawn"):
        return
    binary = fake_chromium(tmp_path)
    done = threading.Event()
    result_box: list = []
    worker = threading.Thread(target=lambda: result_box.append(capture_browser_googlevideo(
        done.is_set, browser=binary, max_seconds=4.0,
    )))
    worker.start()
    for _ in range(100):
        if Path(binary + ".seen").exists():
            break
        time.sleep(0.05)
    assert Path(binary + ".seen").exists(), "fake CDP client never enabled Network"
    done.set()
    worker.join(8)
    assert not worker.is_alive()
    result = result_box[0]
    assert result.hosts == ("rr2---sn-h0jelne7.googlevideo.com", "rr3---sn-h0jelne7.googlevideo.com")
    assert "PRIVATE" not in repr(result) and "LEAKED" not in repr(result)
    # TemporaryDirectory is removed even on normal completion.
    assert not Path(Path(binary + ".profile").read_text()).exists()


def test_cdp_cancellation_reaps_child(tmp_path: Path):
    if os.name != "posix" or not hasattr(os, "posix_spawn"):
        return
    binary = fake_chromium(tmp_path)
    stop = threading.Event()
    result_box: list = []
    thread = threading.Thread(target=lambda: result_box.append(capture_browser_googlevideo(
        lambda: False, cancelled=stop.is_set, browser=binary, max_seconds=6,
    )))
    thread.start()
    time.sleep(0.3)
    stop.set()
    thread.join(8)
    assert not thread.is_alive()
    assert result_box[0].status == "cancelled"


def test_gui_integration_is_explicit_one_shot_without_qthread_subclass():
    source = (Path(__file__).resolve().parents[1] / "gui/zap2_gui/widgets/blockcheck_lab.py").read_text()
    assert "blockcheckCdpCollectButton" in source
    assert "blockcheckCdpFinishButton" in source
    assert "blockcheckCdpResetButton" in source
    assert "capture_browser_googlevideo(" in source
    assert "merge_browser_googlevideo_hosts(" in source
    assert 'state["cdp_hosts"] = ()' in source
    assert 'QtCore.QThread(' not in source
