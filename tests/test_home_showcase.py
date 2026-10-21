from __future__ import annotations

import json
from pathlib import Path

import pytest

from zap2_gui.widgets.home import SHOWCASE_PATH, load_showcase, showcase_html

ROOT = Path(__file__).resolve().parents[1]


def test_showcase_text_is_data_and_refrain_appears_once() -> None:
    data = json.loads(SHOWCASE_PATH.read_text(encoding="utf-8"))
    assert data["formatVersion"] == 1
    assert data["refrain"] == "i just trying.."
    everything = json.dumps(data, ensure_ascii=False)
    assert everything.count("i just trying") == 1
    # Тур по возможностям будет интерактивным; статичного списка «что здесь есть» на витрине нет.
    assert "Что здесь есть" not in everything


def test_showcase_credits_name_core_and_reference_gui() -> None:
    data = load_showcase()
    names = [c["name"] for c in data["credits"]]
    assert names[:2] == ["bol-van", "loop-uh"]
    also = " ".join(a["name"] for a in data["also"])
    for internal in ("p2pKanban", "devctl", "netdiag"):
        assert internal not in json.dumps(data, ensure_ascii=False)
    assert "Tor Project" in also


def test_showcase_html_escapes_and_links_only_https() -> None:
    body = showcase_html({"lead": "<b>x</b>", "paragraphs": [], "credits": [{"name": "a", "text": "t", "url": "javascript:alert(1)"}], "also": [{"name": "w", "url": "https://example.org"}]})
    assert "&lt;b&gt;x&lt;/b&gt;" in body
    assert "javascript:" not in body
    assert 'href="https://example.org"' in body


def test_broken_showcase_falls_back(tmp_path: Path) -> None:
    broken = tmp_path / "showcase.json"
    broken.write_text("{", encoding="utf-8")
    assert load_showcase(broken)["title"] == "z2guiflin"


def test_home_page_does_not_touch_network() -> None:
    source = (ROOT / "gui/zap2_gui/widgets/home.py").read_text(encoding="utf-8")
    for module in ("subprocess", "socket", "urllib", "http.client", "adapters"):
        assert f"import {module}" not in source and f"from {module}" not in source
        assert f"from ..{module}" not in source


def test_home_page_renders_and_starts_diagnostics(monkeypatch) -> None:
    pytest.importorskip("PyQt6")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication, QLabel, QPushButton
    from zap2_gui.widgets.home import make_home_page

    app = QApplication.instance() or QApplication([])
    calls: list[int] = []
    page = make_home_page(on_start=lambda: calls.append(1))
    assert "bol-van" in page.findChild(QLabel, "homeShowcaseText").text()
    assert "i just trying.." in page.findChild(QLabel, "homeRefrain").text()
    page.findChild(QPushButton, "homeStartDiagnostics").click()
    assert calls == [1]
    assert make_home_page().findChild(QPushButton, "homeStartDiagnostics") is None
    app.processEvents()
