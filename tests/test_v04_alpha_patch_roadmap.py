from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_historical_v04_roadmap_keeps_original_service_choice() -> None:
    text = (ROOT / "docs" / "V04_ALPHA_PATCH_ROADMAP.md").read_text(encoding="utf-8")

    assert "Историческая дорожная карта" in text
    assert "youtube-basic" in text
    assert "discord-desktop" in text
    assert "custom" in text
    assert "Одновременная работа YouTube и Discord не являлась критерием готовности" in text


def test_historical_v04_roadmap_points_to_release_boundary() -> None:
    roadmap = (ROOT / "docs" / "V04_ALPHA_PATCH_ROADMAP.md").read_text(encoding="utf-8")
    release = (ROOT / "docs" / "V04_RELEASE.md").read_text(encoding="utf-8")

    assert "принято как `v0.4`" in roadmap
    assert "не универсального сетевого результата" in roadmap
    assert "не является критерием релиза" in release
    assert "stage-нумерацию" in roadmap
