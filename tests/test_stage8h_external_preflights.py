from __future__ import annotations

import stat
from pathlib import Path

from zap2_gui.adapters.discord_tunnel import (
    discord_tunnel_core_preflight_to_text,
    tunnel_connection_import_vless_to_text,
)
from zap2_gui.adapters.strategy_parser_preflight import strategy_parser_preflight_to_text

SAMPLE_VLESS = (
    "vless://11111111-2222-4333-8444-555555555555@example.net:443"
    "?security=tls&encryption=none&type=ws&path=%2Fws&sni=edge.example.org#Stage8h"
)


def _executable(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def test_xray_core_preflight_uses_upstream_test_mode_without_persistent_start(tmp_path: Path) -> None:
    tunnel_connection_import_vless_to_text(SAMPLE_VLESS, root=tmp_path)
    fake_xray = _executable(
        tmp_path / "xray",
        "#!/bin/sh\n"
        "if [ \"$1\" = run ] && [ \"$2\" = -test ] && [ \"$3\" = -config ] && [ -f \"$4\" ]; then\n"
        "  echo 'Configuration OK.'\n"
        "  exit 0\n"
        "fi\n"
        "echo 'unexpected argv' >&2\n"
        "exit 9\n",
    )

    text = discord_tunnel_core_preflight_to_text(root=tmp_path, core_binary=str(fake_xray), core_kind="xray", socks_port=19080)

    assert "Discord tunnel core preflight" in text
    assert "verdict: PASS" in text
    assert "Configuration OK." in text
    assert "starts persistent core/listener: no" in text
    assert "11111111-2222-4333-8444-555555555555" not in text
    assert "example.net" not in text
    generated = tmp_path / ".zap2" / "tunnel" / "generated" / "default.core.json"
    assert generated.exists()
    assert stat.S_IMODE(generated.stat().st_mode) == 0o600


def test_xray_core_preflight_surfaces_core_validation_failure(tmp_path: Path) -> None:
    tunnel_connection_import_vless_to_text(SAMPLE_VLESS, root=tmp_path)
    fake_xray = _executable(
        tmp_path / "xray",
        "#!/bin/sh\necho 'Failed to start: invalid config' >&2\nexit 23\n",
    )

    text = discord_tunnel_core_preflight_to_text(root=tmp_path, core_binary=str(fake_xray), core_kind="xray")

    assert "exit code: 23" in text
    assert "verdict: FAIL" in text
    assert "invalid config" in text


def test_strategy_parser_preflight_runs_nfqws2_dry_run_only(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    fake_nfqws2 = _executable(
        tmp_path / "nfqws2",
        "#!/bin/sh\n"
        "found=0\n"
        "for arg in \"$@\"; do\n"
        "  [ \"$arg\" = --dry-run ] && found=1\n"
        "done\n"
        "if [ \"$found\" = 1 ]; then\n"
        "  echo 'command line parameters verified'\n"
        "  exit 0\n"
        "fi\n"
        "exit 8\n",
    )

    text = strategy_parser_preflight_to_text(root=root, nfqws2_binary=str(fake_nfqws2))

    assert "Strategy parser preflight" in text
    assert "mode: nfqws2 --dry-run" in text
    assert "verdict: PASS" in text
    assert "command line parameters verified" in text
    assert "requires sudo: no" in text
    assert "mutates nftables/NFQUEUE: no" in text
    assert "does not initialize Lua on Linux" in text


def test_sing_box_plan_is_blocked_until_native_config_generator_exists(tmp_path: Path) -> None:
    from zap2_gui.adapters.discord_tunnel import discord_tunnel_plan_to_text

    tunnel_connection_import_vless_to_text(SAMPLE_VLESS, root=tmp_path)
    fake_sing_box = _executable(tmp_path / "sing-box", "#!/bin/sh\nexit 0\n")

    try:
        discord_tunnel_plan_to_text(root=tmp_path, core_binary=str(fake_sing_box), core_kind="sing-box")
    except ValueError as exc:
        text = str(exc)
    else:
        raise AssertionError("sing-box plan must be blocked while only Xray/V2Ray JSON is generated")

    assert "sing-box tunnel plan временно заблокирован" in text
    assert "native sing-box generator" in text
