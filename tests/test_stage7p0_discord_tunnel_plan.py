from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


PRIVATE_TOKENS = (
    "47c87a37" + "-3d09-4c3d-96fb-91ce3bcae058",
    "62.60" + ".148.226",
)


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_tunnel_plan_documents_external_core_lane() -> None:
    text = _text("docs/history/stages/DISCORD_TUNNEL_SOCKS_VLESS_PLAN.md")

    assert "SOCKS5/VLESS tunnel lane" in text
    assert "не реализует VLESS самостоятельно" in text
    assert "xray" in text
    assert "v2ray" in text
    assert "sing-box" in text
    assert "loopback SOCKS5" in text
    assert "TUN/TProxy" in text
    assert "research plan" in text


def test_tunnel_docs_keep_secrets_out_of_repo() -> None:
    paths = [
        "docs/history/stages/DISCORD_TUNNEL_SOCKS_VLESS_PLAN.md",
        "docs/history/stages/V2RAYNG_REFERENCE_NOTES.md",
        "references/external/snippets/stage7p0-v2rayng-socks-vless-notes.txt",
        "PATCH_SUMMARY.md",
    ]
    joined = "\n".join(_text(path) for path in paths)

    for token in PRIVATE_TOKENS:
        assert token not in joined
    assert "vless://<uuid>@<server>:<port>" in joined
    assert ".zap2/tunnel" in joined
    assert "redacted" in joined.lower()


def test_v2rayng_reference_is_reference_only() -> None:
    text = _text("docs/history/stages/V2RAYNG_REFERENCE_NOTES.md")
    snippet = _text("references/external/snippets/stage7p0-v2rayng-socks-vless-notes.txt")

    assert "GPL-3.0" in text
    assert "не копируется" in text
    assert "Android/Kotlin" in text
    assert "do not copy implementation code" in snippet
    assert "loopback SOCKS" in snippet


def test_historical_roadmap_records_tunnel_lane() -> None:
    text = _text("docs/history/stages/V04_ALPHA_PATCH_ROADMAP.md")

    assert "SOCKS5/VLESS" in text
    assert "внешним core" in text
    assert "HAR" in text
    assert "v0.4" in text
