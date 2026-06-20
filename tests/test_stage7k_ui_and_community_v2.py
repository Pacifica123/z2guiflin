from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_blockcheck_lab_is_scrollable_and_uses_two_pane_stage7r_layout() -> None:
    source = (ROOT / "gui" / "zap2_gui" / "widgets" / "blockcheck_lab.py").read_text(encoding="utf-8")

    assert "QScrollArea" in source
    assert "blockcheckLabScrollArea" in source
    assert "scroll.setWidgetResizable(True)" in source
    assert "BLOCKCHECK_LAB_CONTENT_WIDTH = 1160" in source
    assert "BLOCKCHECK_LAB_OUTPUT_MIN_HEIGHT = 300" in source
    assert "BLOCKCHECK_LAB_SIDE_MIN_WIDTH = 360" in source
    assert "form_box.setMinimumWidth(BLOCKCHECK_LAB_SECTION_MIN_WIDTH)" in source
    assert "actions_box.setMinimumWidth(BLOCKCHECK_LAB_SIDE_MIN_WIDTH)" in source
    assert "output.setMinimumWidth(BLOCKCHECK_LAB_SIDE_MIN_WIDTH)" in source
    assert "BLOCKCHECK_LAB_SECTION_MIN_WIDTH = 560" in source
    assert "blockcheckTwoPaneBody" in source
    assert "blockcheckRightColumn" in source
    assert "layout.addWidget(body, 1)" in source
    assert "body_layout.addWidget(form_box, 3, QtCore.Qt.AlignmentFlag.AlignTop)" in source
    assert "form_box.setMinimumWidth(BLOCKCHECK_LAB_CONTENT_WIDTH)" not in source
    assert "output.setMinimumWidth(BLOCKCHECK_LAB_CONTENT_WIDTH)" not in source


def test_main_window_stage7k_size_keeps_diagnostics_roomy() -> None:
    source = (ROOT / "gui" / "zap2_gui" / "windows" / "main_window.py").read_text(encoding="utf-8")

    assert "self.resize(1240, 840)" in source
    assert "self.setMinimumSize(960, 680)" in source


def test_community_discord_syndata_edge_flow_v2_is_registered() -> None:
    catalog = json.loads((ROOT / "strategies" / "catalog.json").read_text(encoding="utf-8"))
    assert "strategies/community-discord-syndata-edge-flow-v2.json" in catalog["strategyFiles"]

    strategy = json.loads((ROOT / "strategies" / "community-discord-syndata-edge-flow-v2.json").read_text(encoding="utf-8"))
    args = strategy["runtimeArgs"]
    assert strategy["id"] == "community-discord-syndata-edge-flow-v2"
    assert "--payload=empty" in args
    assert "--out-range=<s1" in args
    assert "--lua-desync=send:tcp_md5:repeats=2" in args
    assert "--out-range=s1<d1" in args
    assert "--lua-desync=syndata:blob=fake_default_tls:tls_mod=rnd,dupsid,rndsni" in args
    assert any("updates.discord.com,discord.com" in item for item in args)
    assert any("youtube.com,www.youtube.com" in item for item in args)


def test_stage7k_documents_owner_result_split() -> None:
    doc = (ROOT / "docs" / "DISCORD_COMMUNITY_EDGE_FLOW_RESULTS.md").read_text(encoding="utf-8")

    assert "helped YouTube" in doc
    assert "did not move Discord desktop" in doc
    assert "SYN-SENT" in doc
    assert "community-discord-syndata-edge-flow-v2" in doc
