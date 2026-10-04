"""HAR sanitizer: no planted secret survives, network evidence stays usable."""
from __future__ import annotations

import gzip
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import quote

import pytest

from zap2_gui.adapters import har_sanitizer as sanitizer
from zap2_gui.adapters.har_discovery import analyze_har
from zap2_gui.adapters.har_sanitizer import (
    HarSanitizeError,
    SanitizeOptions,
    default_output_path,
    looks_random,
    sanitize_har_data,
    sanitize_har_file,
)
from zap2_gui.adapters.har_workbench import build_har_workbench
from zap2_gui.widgets import blockcheck_lab

ROOT = Path(__file__).resolve().parents[1]
MEDIA_HOST = "rr8---sn-n8v7znlr.googlevideo.com"
SECRETS = {
    "cookie": "g.a000mQhK3xYz9Lp2Vt8WnRb5Dc7Fj1Hs4Ku6Mo0Qe3Ty",
    "visitor": "CgtQbTNhWnJ4VjdLOCiA4pG5BjIKCgJSVRIEGgAgOQ",
    "video": "dQw4w9WgXcQ",
    "signature": "AJfQdSswRQIhAL3kQ9vXw7Zp1Nf5Tg8Ur2Yb6Hc4Me0Jd",
    "client_ip": "198.51.100.77",
    "email": "john.private@example.org",
    "search": "секретный запрос",
    "body": "PRIVATE-BODY-CANARY",
    "token": "MTIzNDU2Nzg5MDEyMzQ1Njc4.GaBcDe.fGhIjKlMnOpQrStUvWxYz0123456789AbCdEf",
    "channel": "987654321098765432",
    "message": "111222333444555666",
    "user": "123456789012345678",
    "super": "eyJvcyI6IkxpbnV4IiwiYnJvd3NlciI6IkZpcmVmb3giLCJkZXZpY2UiOiIifQ==",
    "attachment": "passport_scan_ivanov",
    "username": "ivan_petrov_1990",
    "password": "hunter2hunter2",
    "ws": "CANARY-WS-IDENTIFY",
    "jwt": "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV",
    "extension": "3f9c2b1a-7d6e-4c5b-8a9f-0e1d2c3b4a59",
    "note": "private free text note",
    "title": "Мой приватный плейлист",
}
S = SECRETS
FIREFOX_UA = "Mozilla/5.0 (X11; Linux x86_64; rv:131.0) Gecko/20100101 Firefox/131.0"


def _header(name: str, value: str) -> dict[str, str]:
    return {"name": name, "value": value}


def _entry(method: str, url: str, status: int, *, started: str, **extra: object) -> dict[str, object]:
    request: dict[str, object] = {
        "method": method, "url": url, "httpVersion": "HTTP/2", "headers": extra.pop("request_headers", []),
        "cookies": extra.pop("request_cookies", []), "queryString": extra.pop("query", []), "headersSize": 100, "bodySize": 0,
    }
    if "post" in extra:
        request["postData"] = extra.pop("post")
    response: dict[str, object] = {
        "status": status, "statusText": extra.pop("status_text", "OK" if status == 200 else ""),
        "httpVersion": extra.pop("response_version", "HTTP/2"), "headers": extra.pop("response_headers", []), "cookies": [],
        "content": extra.pop("content", {"size": 0, "mimeType": "x-unknown"}), "redirectURL": extra.pop("redirect", ""),
        "headersSize": 0, "bodySize": 0,
    }
    if "response_error" in extra:
        response["_error"] = extra.pop("response_error")
    return {
        "pageref": "page_1", "startedDateTime": started, "request": request, "response": response, "cache": {},
        "timings": {"blocked": 0, "dns": 3, "connect": 20, "ssl": 25, "send": 0, "wait": 180, "receive": 44}, "time": 272, **extra,
    }


def _har() -> dict[str, object]:
    """Firefox-like YouTube capture and Chrome-like Discord capture in one HAR."""
    cookie = f"SID={S['cookie']}; VISITOR_INFO1_LIVE=Pm3aZrxV7K8; PREF=tz=Asia.Krasnoyarsk"
    videoplayback = (
        f"https://{MEDIA_HOST}/videoplayback?expire=1727791600&ip={S['client_ip']}&itag=248&mime=video%2Fwebm"
        f"&sig={S['signature']}&range=0-1048575&rn=5&c=WEB"
    )
    discord_api = f"https://discord.com/api/v9/channels/{S['channel']}/messages?limit=50&before={S['message']}"
    entries = [
        _entry(
            "GET", f"https://www.youtube.com/watch?v={S['video']}&list=PLprivate123", 200, started="2026-10-01T10:15:02.123+07:00",
            request_headers=[
                _header("Host", "www.youtube.com"), _header("User-Agent", FIREFOX_UA), _header("Cookie", cookie),
                _header("Authorization", f"SAPISIDHASH 1727770000_{S['signature']}"), _header("X-Goog-Visitor-Id", S["visitor"]),
                _header("Accept-Language", "ru-RU,ru;q=0.8"), _header("Sec-Fetch-Mode", "cors"),
            ],
            request_cookies=[{"name": "SID", "value": S["cookie"], "path": "/", "domain": ".youtube.com", "httpOnly": True}],
            query=[{"name": "v", "value": S["video"]}, {"name": "list", "value": "PLprivate123"}],
            response_headers=[
                _header("content-type", "text/html; charset=utf-8"), _header("server", "ESF"),
                _header("alt-svc", 'h3=":443"; ma=2592000'), _header("date", "Thu, 01 Oct 2026 03:15:02 GMT"),
                _header("set-cookie", f"YSC=xQ3vT9kLm2Z; Domain=.youtube.com; Path=/; Secure; HttpOnly\nVMD={S['visitor']}; Path=/"),
            ],
            content={"size": 987654, "mimeType": "text/html; charset=utf-8", "text": f"<title>{S['title']}</title>{S['body']} {S['email']}"},
            serverIPAddress="142.250.74.110", connection="443", _securityState="secure",
        ),
        _entry(
            "POST", "https://www.youtube.com/youtubei/v1/player?prettyPrint=false", 200, started="2026-10-01T10:15:03.500+07:00",
            request_headers=[_header("Content-Type", "application/json"), _header("Cookie", cookie)],
            post={"mimeType": "application/json", "text": json.dumps({"videoId": S["video"], "visitorData": S["visitor"], "q": S["search"]}, ensure_ascii=False)},
            content={"size": 250000, "mimeType": "application/json", "text": json.dumps({"videoId": S["video"], "x": S["body"]})},
            serverIPAddress="142.250.74.110",
        ),
        _entry(
            "GET", videoplayback, 0, started="2026-10-01T10:15:04.000+07:00", status_text="", response_version="",
            request_headers=[_header("Host", MEDIA_HOST), _header("Referer", f"https://www.youtube.com/watch?v={S['video']}")],
            response_error="NS_ERROR_NET_RESET", serverIPAddress="2a00:1450:4010:c0e::84",
        ),
        _entry(
            "GET", videoplayback.replace("itag=248", "itag=251"), 0, started="2026-10-01T10:15:04.200+07:00",
            status_text="NS_BINDING_ABORTED", _error="NS_BINDING_ABORTED",
        ),
        _entry(
            "GET", f"https://i.ytimg.com/vi/{S['video']}/hqdefault.jpg?sqp=-oaymwEcCNACELwBSFXyq4qpAw4IARUAAIhCGAFwAcABBg==", 200,
            started="2026-10-01T10:15:05.000+07:00",
            content={"size": 20500, "mimeType": "image/jpeg", "encoding": "base64", "text": "/9j/4AAQSkZJRgABAQAAAQABAAD" * 4},
        ),
        _entry(
            "GET", discord_api, 200, started="2026-10-01T03:15:06.000Z",
            request_headers=[
                _header(":authority", "discord.com"), _header(":path", discord_api.split("discord.com", 1)[1]),
                _header("authorization", S["token"]), _header("x-super-properties", S["super"]),
                _header("referer", f"https://discord.com/channels/555666777888999000/{S['channel']}"),
            ],
            query=[{"name": "limit", "value": "50"}, {"name": "before", "value": S["message"]}],
            response_headers=[_header("cf-ray", "8cb1a2b3c4d5e6f7-DME"), _header("server", "cloudflare"), _header("x-ratelimit-remaining", "4")],
            content={"size": 4096, "mimeType": "application/json", "text": json.dumps([{"content": S["body"], "author": {"id": S["user"], "email": S["email"]}}])},
            serverIPAddress="162.159.128.233", _resourceType="xhr", _priority="High",
            _initiator={"type": "script", "stack": {"callFrames": [{"functionName": "fetchMessages", "url": "https://discord.com/assets/web.8f3a9c1e2b7d4f60.js", "lineNumber": 1}]}},
        ),
        _entry(
            "POST", "https://discord.com/api/v9/auth/login", 401, started="2026-10-01T03:15:07.000Z",
            post={"mimeType": "application/json", "text": json.dumps({"login": S["email"], "password": S["password"]})},
            content={"size": 60, "mimeType": "application/json", "text": json.dumps({"message": "401: Unauthorized", "token": S["token"], "ip": S["client_ip"]})},
        ),
        _entry(
            "GET", "wss://gateway.discord.gg/?encoding=json&v=10&compress=zlib-stream", 101, started="2026-10-01T03:15:08.000Z",
            status_text="Switching Protocols", response_version="HTTP/1.1",
            query=[{"name": "encoding", "value": "json"}, {"name": "v", "value": "10"}],
            _webSocketMessages=[{"type": "send", "time": 1790824508.1, "opcode": 1, "data": json.dumps({"token": S["token"], "m": S["ws"]})}],
        ),
        _entry(
            "GET", f"https://cdn.discordapp.com/attachments/{S['channel']}/{S['message']}/{S['attachment']}.pdf?ex=670a1b2c&hm=9f8e7d6c5b4a3928", 0,
            started="2026-10-01T03:15:09.000Z", status_text="", response_version="", response_error="net::ERR_QUIC_PROTOCOL_ERROR",
        ),
        _entry(
            "GET", f"https://ivan:{S['password']}@discord.com/users/{S['username']}/profile#access_token={S['jwt']}", 302,
            started="2026-10-01T03:15:10.000Z", request_headers=[_header("authorization", f"Bearer {S['jwt']}"), _header("x-forwarded-for", S["client_ip"])],
            response_headers=[_header("location", f"https://discord.com/login?token={S['jwt']}")], redirect=f"https://discord.com/login?token={S['jwt']}",
            _customNote=S["note"], _sessionToken=S["token"], _debug={S["user"]: "x", "trace": [S["client_ip"]]},
        ),
        _entry("GET", f"moz-extension://{S['extension']}/content/inject.js", 200, started="2026-10-01T03:15:11.000Z"),
    ]
    pages = [{"startedDateTime": "2026-10-01T10:15:02.000+07:00", "id": "page_1", "title": f"https://www.youtube.com/watch?v={S['video']}",
              "pageTimings": {"onContentLoad": 1500, "onLoad": 3200}}]
    return {"log": {"version": "1.2", "creator": {"name": "Firefox", "version": "131.0"}, "pages": pages, "entries": entries}}


def _assert_no_secret(text: str) -> None:
    for name, secret in SECRETS.items():
        for variant in {secret, quote(secret, safe=""), json.dumps(secret)[1:-1]}:
            assert variant not in text, name


def _urls(data: dict[str, object]) -> list[str]:
    return [entry["request"]["url"] for entry in data["log"]["entries"]]


def _copy_project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    shutil.copytree(ROOT, project, ignore=shutil.ignore_patterns(".git", ".zap2", "__pycache__", "*.pyc", ".pytest_cache"))
    return project


def test_balanced_profile_removes_planted_secrets_and_keeps_network_evidence() -> None:
    result, report = sanitize_har_data(_har(), source_name="capture.har")
    text = json.dumps(result, ensure_ascii=False)
    _assert_no_secret(text)
    assert report.clean and report.leaks_remaining == 0 and report.entries == 11 and report.hosts == 6

    entries = result["log"]["entries"]
    assert [entry["response"]["status"] for entry in entries] == [200, 200, 0, 0, 200, 200, 401, 101, 0, 302, 200]
    assert entries[2]["response"]["_error"] == "NS_ERROR_NET_RESET"
    assert entries[3]["_error"] == "NS_BINDING_ABORTED"
    assert entries[8]["response"]["_error"] == "net::ERR_QUIC_PROTOCOL_ERROR"
    assert entries[0]["serverIPAddress"] == "142.250.74.110" and entries[2]["serverIPAddress"] == "2a00:1450:4010:c0e::84"
    assert entries[0]["timings"]["wait"] == 180 and entries[0]["connection"] == "443"
    assert entries[0]["startedDateTime"] == "2026-10-01T03:15:02.123Z"  # same instant, time zone hidden
    assert f"https://{MEDIA_HOST}/videoplayback?" in entries[2]["request"]["url"]
    for kept in ("itag=248", "mime=video%2Fwebm", "range=0-1048575", "rn=5", "c=WEB", "ip=REDACTED_", "sig=REDACTED_"):
        assert kept in entries[2]["request"]["url"]
    assert entries[7]["request"]["url"] == "wss://gateway.discord.gg/?encoding=json&v=10&compress=zlib-stream"

    headers = {item["name"]: item["value"] for item in entries[0]["request"]["headers"]}
    assert headers["User-Agent"] == "Firefox/131; Linux" and headers["Sec-Fetch-Mode"] == "cors"
    assert headers["Cookie"].startswith("SID=REDACTED_") and "VISITOR_INFO1_LIVE=REDACTED_" in headers["Cookie"]
    assert headers["Authorization"].startswith("REDACTED_") and headers["Accept-Language"].startswith("REDACTED_")
    response_headers = {item["name"]: item["value"] for item in entries[0]["response"]["headers"]}
    assert response_headers["alt-svc"] == 'h3=":443"; ma=2592000' and response_headers["server"] == "ESF"
    assert "Domain=.youtube.com; Path=/; Secure; HttpOnly" in response_headers["set-cookie"]
    assert {item["name"]: item["value"] for item in entries[5]["response"]["headers"]}["cf-ray"].endswith("-DME")
    assert set(report.redacted_headers) >= {"authorization", "x-goog-visitor-id", "x-super-properties", "x-forwarded-for"}
    assert result["log"]["_sanitizer"]["profile"] == "balanced"
    assert "HAR sanitizer: очистка завершена" in report.to_text() and "capture.har" in report.to_text()


def test_bodies_and_websocket_payloads_are_dropped_but_sizes_stay() -> None:
    result, report = sanitize_har_data(_har())
    entries = result["log"]["entries"]
    assert entries[1]["request"]["postData"]["text"] == "" and entries[1]["request"]["postData"]["_sanitized"]["chars"] > 0
    assert entries[1]["request"]["postData"]["mimeType"] == "application/json"
    assert "text" not in entries[0]["response"]["content"] and entries[0]["response"]["content"]["size"] == 987654
    assert entries[4]["response"]["content"]["_sanitized"]["encoding"] == "base64"
    message = entries[7]["_webSocketMessages"][0]
    assert message["data"] == "" and message["_dataLength"] > 0 and message["type"] == "send" and message["opcode"] == 1
    assert report.counts["requestBodies"] == 2 and report.counts["webSocketPayloads"] == 1


def test_pseudonyms_are_consistent_shape_preserving_and_keyed() -> None:
    first, _report = sanitize_har_data(_har(), SanitizeOptions(salt="key-one"))
    again, _report = sanitize_har_data(_har(), SanitizeOptions(salt="key-one"))
    other, _report = sanitize_har_data(_har(), SanitizeOptions(salt="key-two"))
    assert first == again and _urls(first) != _urls(other)

    entry = first["log"]["entries"][5]
    channel = entry["request"]["url"].split("/channels/")[1].split("/")[0]
    assert channel.isdigit() and len(channel) == len(S["channel"]) and channel != S["channel"]
    headers = {item["name"]: item["value"] for item in entry["request"]["headers"]}
    assert headers[":path"] == entry["request"]["url"].split("discord.com", 1)[1]
    assert headers["referer"].endswith("/" + channel)
    before = entry["request"]["url"].rsplit("before=", 1)[1]
    assert before.startswith("REDACTED_") and entry["request"]["queryString"][1] == {"name": "before", "value": before}
    assert entry["_initiator"]["stack"]["callFrames"][0]["url"].startswith("https://discord.com/assets/web.")
    video = first["log"]["entries"][4]["request"]["url"].split("/vi/")[1].split("/")[0]
    assert len(video) == 11 and video != S["video"] and first["log"]["entries"][4]["request"]["url"].split("?")[0].endswith("/hqdefault.jpg")
    assert first["log"]["pages"][0]["title"] == first["log"]["entries"][0]["request"]["url"].split("&")[0]
    assert first["log"]["pages"][0]["pageTimings"] == {"onContentLoad": 1500, "onLoad": 3200}


def test_strict_profile_hides_addresses_time_and_every_query_value() -> None:
    result, report = sanitize_har_data(_har(), SanitizeOptions(profile="strict", keep_error_bodies=True))
    _assert_no_secret(json.dumps(result, ensure_ascii=False))
    entries = result["log"]["entries"]
    assert all(entry.get("serverIPAddress", "") == "" for entry in entries) and report.counts["serverIps"] == 4
    assert result["log"]["pages"][0]["startedDateTime"] == "2000-01-01T00:00:00.000Z"
    assert entries[0]["startedDateTime"] == "2000-01-01T00:00:00.123Z"
    assert entries[7]["request"]["url"].count("REDACTED_") == 3
    headers = {item["name"]: item["value"] for item in entries[0]["request"]["headers"]}
    assert headers["User-Agent"].startswith("REDACTED_")
    assert {item["name"]: item["value"] for item in entries[0]["response"]["headers"]}["date"].startswith("REDACTED_")
    assert all("text" not in entry["response"]["content"] for entry in entries)  # strict never keeps bodies
    assert "stack" not in entries[5]["_initiator"] and entries[5]["response"]["status"] == 200
    with pytest.raises(HarSanitizeError):
        SanitizeOptions(profile="unknown")


def test_error_bodies_can_be_kept_after_text_scrubbing() -> None:
    result, report = sanitize_har_data(_har(), SanitizeOptions(keep_error_bodies=True))
    text = json.dumps(result, ensure_ascii=False)
    _assert_no_secret(text)
    body = result["log"]["entries"][6]["response"]["content"]
    assert "401: Unauthorized" in body["text"] and body["_sanitized"]["kept"] == "scrubbed-error-body"
    assert "text" not in result["log"]["entries"][0]["response"]["content"]  # successful responses stay dropped
    assert report.counts["errorBodiesKept"] == 1 and any("тела ошибок" in item for item in report.warnings)


def test_final_pass_catches_secret_repeated_in_allowlisted_fields() -> None:
    token = "Zx9Qv7Lm3Kp1Rt5Wy8Bn2Hd6"
    har = {"log": {"entries": [_entry(
        "GET", "https://api.example.net/v1/items", 500, started="2026-10-01T03:15:02Z", status_text=f"upstream said {token}",
        request_headers=[_header("authorization", token)], response_headers=[_header("server", f"edge {token}"), _header("via", "1.1 proxy")],
    )]}}
    result, report = sanitize_har_data(har)
    assert token not in json.dumps(result) and report.residual_replaced == 2 and report.clean
    assert {item["name"]: item["value"] for item in result["log"]["entries"][0]["response"]["headers"]}["via"] == "1.1 proxy"


def test_identifier_proven_by_position_is_masked_in_other_urls_but_schema_survives() -> None:
    har = {"log": {"entries": [
        _entry("GET", "https://site.example/torvaldsl/linux", 200, started="2026-10-01T03:15:02Z",
               request_headers=[_header("Referer", "https://site.example/torvaldsl"), _header("Upgrade", "websocket")]),
        _entry("GET", "https://site.example/users/torvaldsl/repos", 200, started="2026-10-01T03:15:03Z"),
        _entry("GET", "https://site.example/rooms/websocket", 200, started="2026-10-01T03:15:04Z", _resourceType="websocket"),
        _entry("GET", "https://site.example/api/session/response", 200, started="2026-10-01T03:15:05Z"),
    ]}}
    original = json.dumps(har)
    result, report = sanitize_har_data(har)
    assert json.dumps(har) == original  # the input object is not modified
    assert "torvaldsl" not in json.dumps(result) and report.residual_replaced == 2 and report.clean
    first = result["log"]["entries"][0]
    assert first["request"]["url"].startswith("https://site.example/REDACTED_") and first["request"]["url"].endswith("/linux")
    assert {item["name"]: item["value"] for item in first["request"]["headers"]}["Upgrade"] == "websocket"
    assert result["log"]["entries"][2]["_resourceType"] == "websocket"
    assert all({"request", "response", "startedDateTime"} <= set(entry) for entry in result["log"]["entries"])


def test_unknown_custom_fields_are_default_deny() -> None:
    result, _report = sanitize_har_data(_har())
    entry = result["log"]["entries"][9]
    assert entry["_customNote"].startswith("REDACTED_") and entry["_sessionToken"].startswith("REDACTED_")
    assert all(key.startswith("REDACTED_") or key == "trace" for key in entry["_debug"])
    assert entry["_debug"]["trace"][0].startswith("REDACTED_")
    assert entry["request"]["url"].startswith("https://discord.com/users/") and entry["request"]["url"].endswith("/profile#REDACTED")
    assert result["log"]["entries"][10]["request"]["url"].startswith("moz-extension:REDACTED_")
    assert result["log"]["entries"][5]["_resourceType"] == "xhr" and result["log"]["entries"][5]["_priority"] == "High"
    assert looks_random("dQw4w9WgXcQ") and looks_random("987654321098765432") and looks_random("4f3c2a1b")
    assert not any(looks_random(word) for word in ("onContentLoad", "getAccountInfo", "hqdefault", "VISITOR_INFO1_LIVE", "videoplayback"))


def test_workbench_evidence_is_the_same_for_raw_and_sanitized_har(tmp_path: Path) -> None:
    project = _copy_project(tmp_path)
    raw_path = tmp_path / "capture.har"
    raw_path.write_text(json.dumps(_har(), ensure_ascii=False), encoding="utf-8")
    (report,) = sanitize_har_file(raw_path)
    assert report.output_path == tmp_path / "capture.sanitized.har" and report.output_bytes > 0

    def evidence(path: Path) -> dict[str, dict[str, object]]:
        hosts = {}
        for item in analyze_har(path, root=project).host_summaries:
            if "." not in item.host:
                continue  # the raw summary counts the browser extension id as a host
            payload = item.to_dict()
            payload["pathPatterns"] = len(payload["pathPatterns"])
            hosts[item.host] = payload
        return hosts

    assert evidence(raw_path) == evidence(report.output_path)
    workbench = build_har_workbench(report.output_path, root=project)
    assert "har-googlevideo-com-tls-transport-failure" in {group.group_id for group in workbench.groups}
    _assert_no_secret("\n".join(path.read_text(encoding="utf-8") for path in workbench.workbench_dir.rglob("*.json")))


def test_file_api_reads_zip_and_gzip_and_never_overwrites_the_source(tmp_path: Path) -> None:
    raw = json.dumps(_har(), ensure_ascii=False).encode("utf-8")
    source = tmp_path / "capture.har"
    source.write_bytes(b"\xef\xbb\xbf" + raw)  # UTF-8 BOM is accepted
    with pytest.raises(HarSanitizeError):
        sanitize_har_file(source, source)
    (report,) = sanitize_har_file(source)
    with pytest.raises(HarSanitizeError):
        sanitize_har_file(source)  # existing result is not replaced silently
    assert sanitize_har_file(source, overwrite=True, compact=True)[0].output_bytes < report.output_bytes
    assert source.read_bytes() == b"\xef\xbb\xbf" + raw

    packed = tmp_path / "packed.har.gz"
    packed.write_bytes(gzip.compress(raw))
    assert sanitize_har_file(packed)[0].output_path == tmp_path / "packed.sanitized.har"
    archive = tmp_path / "pair.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("youtube.har", raw)
        handle.writestr("nested/discord.har", raw)
    reports = sanitize_har_file(archive, out_dir=tmp_path / "out", options=SanitizeOptions(salt="batch"))
    assert sorted(item.output_path.name for item in reports) == ["pair.nested.discord.sanitized.har", "pair.youtube.sanitized.har"]
    assert reports[0].output_path.read_bytes() == reports[1].output_path.read_bytes()
    with pytest.raises(HarSanitizeError):
        sanitize_har_file(archive, tmp_path / "single.har")
    assert default_output_path(Path("/x/capture.HAR")).name == "capture.sanitized.har"
    for bad in (b"not json", b'{"log": {}}', b"[]", b"\x1f\x8bbroken"):
        (tmp_path / "bad.har").write_bytes(bad)
        with pytest.raises(HarSanitizeError):
            sanitize_har_file(tmp_path / "bad.har")


def test_command_line_reports_and_exit_codes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = tmp_path / "capture.har"
    source.write_text(json.dumps(_har(), ensure_ascii=False), encoding="utf-8")
    report_path = tmp_path / "report.json"
    assert sanitizer.main([str(source), "--profile", "strict", "--report-json", str(report_path)]) == 0
    printed = capsys.readouterr().out
    assert "профиль: strict" in printed and "осталось подозрительных совпадений — 0" in printed
    _assert_no_secret(printed + report_path.read_text(encoding="utf-8"))
    assert json.loads(report_path.read_text(encoding="utf-8"))[0]["leaksRemaining"] == 0
    assert sanitizer.main([str(source)]) == 2 and "уже существует" in capsys.readouterr().err
    assert sanitizer.main([str(tmp_path / "missing.har"), "-q"]) == 2
    assert sanitizer.main([str(source), str(source), "-o", str(tmp_path / "x.har")]) == 2


def test_sanitizer_file_is_a_standalone_script(tmp_path: Path) -> None:
    script = tmp_path / "har_sanitize.py"
    shutil.copyfile(ROOT / "gui/zap2_gui/adapters/har_sanitizer.py", script)
    source = tmp_path / "capture.har"
    source.write_text(json.dumps(_har(), ensure_ascii=False), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "-I", "-B", str(script), str(source), "--salt", "s", "-o", str(tmp_path / "clean.har")],
        cwd=tmp_path, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    cleaned = (tmp_path / "clean.har").read_text(encoding="utf-8")
    _assert_no_secret(cleaned + result.stdout)
    assert json.loads(cleaned)["log"]["_sanitizer"]["options"]["pseudonymKey"] == "user-salt"


def _fake_qt(source: str, choice: tuple[str, bool], destination: str) -> SimpleNamespace:
    calls: list[str] = []

    def record(name: str, value: object):
        def call(*_args: object, **_kwargs: object) -> object:
            calls.append(name)
            return value
        return call

    return SimpleNamespace(
        calls=calls,
        QFileDialog=SimpleNamespace(getOpenFileName=record("open", (source, "")), getSaveFileName=record("save", (destination, ""))),
        QInputDialog=SimpleNamespace(getItem=record("profile", choice)),
    )


def test_gui_dialog_writes_sanitized_copy_and_respects_cancel(tmp_path: Path) -> None:
    source = tmp_path / "capture.har"
    source.write_text(json.dumps(_har(), ensure_ascii=False), encoding="utf-8")
    target = tmp_path / "clean.har"
    strict_label = blockcheck_lab.HAR_SANITIZE_PROFILE_CHOICES[1][0]

    qt = _fake_qt(str(source), (strict_label, True), str(target))
    text, status = blockcheck_lab.run_har_sanitize_dialog(qt, None, tmp_path)
    assert qt.calls == ["open", "profile", "save"] and status == "Статус: HAR очищен"
    assert "профиль: strict" in text and str(target) in text and "HAR import" in text
    _assert_no_secret(target.read_text(encoding="utf-8") + text)
    assert json.loads(target.read_text(encoding="utf-8"))["log"]["_sanitizer"]["profile"] == "strict"

    for cancelled in (_fake_qt("", (strict_label, True), str(target)), _fake_qt(str(source), (strict_label, False), str(target)),
                      _fake_qt(str(source), (strict_label, True), "")):
        assert blockcheck_lab.run_har_sanitize_dialog(cancelled, None, tmp_path) is None
    text, status = blockcheck_lab.run_har_sanitize_dialog(_fake_qt(str(source), (strict_label, True), str(source)), None, tmp_path)
    assert "ошибка" in text and "не перезаписывается" in text and "ошибкой" in status
    assert source.read_text(encoding="utf-8") == json.dumps(_har(), ensure_ascii=False)


def test_gui_source_wires_the_button_without_new_cli_or_action_contract() -> None:
    source = (ROOT / "gui/zap2_gui/widgets/blockcheck_lab.py").read_text(encoding="utf-8")
    assert 'har_sanitize_button = QtWidgets.QPushButton("HAR sanitize")' in source
    assert 'har_sanitize_button.setObjectName("blockcheckHarSanitizeButton")' in source
    assert "(har_sanitize_button, 9, 0, 1, 2)" in source and "(voice_profiles_button, 8, 1, 1, 1)" in source
    assert "har_sanitize_button.clicked.connect(lambda _checked=False: sanitize_har_copy())" in source
    assert source.count("voice_profiles_button, har_sanitize_button,") == 2  # sizing loop and running-state lock
    assert "har_sanitizer" not in (ROOT / "gui/zap2_gui/app.py").read_text(encoding="utf-8")
    assert "gui/zap2_gui/adapters/har_sanitizer.py" in json.loads((ROOT / "packaging/release-files.json").read_text())["files"]
    adapter = (ROOT / "gui/zap2_gui/adapters/har_sanitizer.py").read_text(encoding="utf-8")
    assert "zap2_gui" not in adapter.split('"""', 2)[2] and "from ." not in adapter  # stdlib only, no package imports


def test_gui_button_runs_sanitizer_in_real_qt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("PyQt6")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    from PyQt6 import QtWidgets

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    project = _copy_project(tmp_path)
    source = tmp_path / "capture.har"
    source.write_text(json.dumps(_har(), ensure_ascii=False), encoding="utf-8")
    target = tmp_path / "clean.har"
    page = blockcheck_lab.make_blockcheck_lab_page(project)
    button = page.findChild(QtWidgets.QPushButton, "blockcheckHarSanitizeButton")
    assert button is not None and button.isEnabled() and button.text() == "HAR sanitize"
    fake = _fake_qt(str(source), (blockcheck_lab.HAR_SANITIZE_PROFILE_CHOICES[0][0], True), str(target))
    monkeypatch.setattr(QtWidgets, "QFileDialog", fake.QFileDialog)
    monkeypatch.setattr(QtWidgets, "QInputDialog", fake.QInputDialog)
    button.click()
    app.processEvents()
    assert fake.calls == ["open", "profile", "save"] and target.is_file()
    assert "HAR sanitizer: очистка завершена" in page.findChild(QtWidgets.QPlainTextEdit, "blockcheckOutput").toPlainText()
    assert page.findChild(QtWidgets.QLabel, "blockcheckStatusPill").text() == "Статус: HAR очищен"
    _assert_no_secret(target.read_text(encoding="utf-8"))
    page.close()
