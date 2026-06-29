from __future__ import annotations

import stat
from pathlib import Path

from zap2_gui.adapters.launch_composer import launch_composer_start_to_text, launch_composer_status_to_text
from zap2_gui.adapters.launch_error_classifier import classify_launch_issue
from zap2_gui.adapters.discord_tunnel import tunnel_connection_import_vless_to_text


SAMPLE_VLESS = (
    "vless://11111111-2222-4333-8444-555555555555@example.net:8080"
    "?security=none&encryption=none&type=tcp&host=www.example.org&headerType=http#Sample"
)


def _executable(path: Path, body: str = "#!/bin/sh\nsleep 30\n") -> Path:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def test_launch_composer_reports_nfqw2_build_needed_before_partial_start(tmp_path: Path) -> None:
    tunnel_connection_import_vless_to_text(SAMPLE_VLESS, root=tmp_path)
    fake_core = _executable(tmp_path / "v2ray")

    status = launch_composer_status_to_text(
        root=tmp_path,
        components="zapret-default,tunnel-vless",
        core_binary=str(fake_core),
    )
    assert "zapret-default" in status
    assert "ready=needs nfqws2 build" in status

    text = launch_composer_start_to_text(
        root=tmp_path,
        components="zapret-default,tunnel-vless",
        core_binary=str(fake_core),
    )

    assert "Launch composer start: blocked" in text
    assert "- zapret-default: needs nfqws2 build" in text
    assert "No components were started" in text
    assert "tunnel-vless: start external core" not in text
    assert not (tmp_path / ".zap2" / "tunnel" / "runtime" / "default.session.json").exists()


def test_launch_classifier_prefers_specific_zapret_binary_code() -> None:
    issue = classify_launch_issue(
        action="Combined toggle start",
        text="Default start заблокирован до privileged start: nfqws2 binary отсутствует или не исполняемый.",
        selected_status="Zapret default: stopped/needs nfqws2 build; VLESS tunnel: running/ready",
        all_selected_running=False,
    )

    assert issue is not None
    assert issue.code == "Z2-ZAPRET-BINARY-MISSING"
    assert "nfqws2" in issue.full_text()
