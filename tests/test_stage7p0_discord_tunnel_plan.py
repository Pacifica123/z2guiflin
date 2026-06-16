from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


PRIVATE_TOKENS = (
    "47c87a37" + "-3d09-4c3d-96fb-91ce3bcae058",
    "62.60" + ".148.226",
)


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_stage7p0_tunnel_plan_documents_new_lane() -> None:
    text = _text("docs/DISCORD_TUNNEL_SOCKS_VLESS_PLAN.md")

    assert "Stage 7p0" in text
    assert "SOCKS/VLESS tunnel" in text
    assert "orchestrate an external core" in text
    assert "do not implement VLESS" in text
    assert "Updater-window via local SOCKS" in text
    assert "Discord checks updates on every launch" in text
    assert "T0_CORE_ONLY" in text
    assert "T4_APP_USABLE" in text


def test_stage7p0_plan_keeps_secrets_out_of_repo() -> None:
    paths = [
        "docs/DISCORD_TUNNEL_SOCKS_VLESS_PLAN.md",
        "docs/V2RAYNG_REFERENCE_NOTES.md",
        "references/external/snippets/stage7p0-v2rayng-socks-vless-notes.txt",
        "PATCH_SUMMARY.md",
    ]
    joined = "\n".join(_text(path) for path in paths)

    for token in PRIVATE_TOKENS:
        assert token not in joined
    assert "vless://<uuid>@<server>:<port>" in joined
    assert ".zap2/tunnel" in joined
    assert "redact" in joined.lower() or "redacted" in joined.lower()


def test_stage7p0_v2rayng_reference_is_reference_only() -> None:
    text = _text("docs/V2RAYNG_REFERENCE_NOTES.md")
    snippet = _text("references/external/snippets/stage7p0-v2rayng-socks-vless-notes.txt")

    assert "GPL-3.0" in text
    assert "concepts, not copied code" in text
    assert "VlessFmt.kt" in text
    assert "CoreProxyOnlyService.kt" in text
    assert "do not copy implementation code" in snippet
    assert "loopback SOCKS" in snippet


def test_stage7p0_roadmap_mentions_discord_tunnel_lane() -> None:
    text = _text("docs/V04_ALPHA_PATCH_ROADMAP.md")

    assert "Stage 7p0" in text
    assert "Discord SOCKS/VLESS tunnel" in text
    assert "zapret direct strategy" in text
    assert "external core" in text
    assert "no automatic external downloads" in text
