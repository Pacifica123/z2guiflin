from __future__ import annotations

import json
from pathlib import Path

import pytest

from zap2_gui.adapters import net_verdict
from zap2_gui.models.navigation import NAVIGATION_GROUPS, default_navigation_sections
from zap2_gui.models.remedy import REMEDIES, VERDICT_REMEDIES, remedies_for_verdict, remedy_hint

ROOT = Path(__file__).resolve().parents[1]


def test_every_verdict_code_has_a_remedy_entry() -> None:
    codes = {value for name, value in vars(net_verdict).items() if name.startswith("VERDICT_") and isinstance(value, str)}
    assert codes == set(VERDICT_REMEDIES)
    for keys in VERDICT_REMEDIES.values():
        assert all(key in REMEDIES for key in keys)


def test_remedies_point_to_existing_pages_only() -> None:
    keys = {section.key for section in default_navigation_sections()}
    for remedy in REMEDIES.values():
        assert remedy.page_key is None or remedy.page_key in keys, remedy.key
        assert remedy.what_changes and remedy.title


def test_verdict_to_remedy_mapping_matches_layers() -> None:
    assert [r.key for r in remedies_for_verdict("DPI_SELECTIVE")] == ["zapret", "presets"]
    assert [r.key for r in remedies_for_verdict("IP_BLOCK")] == ["tunnel"]
    assert remedies_for_verdict("OK") == ()
    assert remedies_for_verdict("nonsense") == ()
    # Локальная поломка: честно говорим, что обход блокировок не поможет.
    local = remedies_for_verdict("LOCAL_NO_ROUTE")
    assert local and all(r.page_key is None for r in local)
    assert "root" in remedy_hint(REMEDIES["zapret"])


def test_navigation_groups_are_known_and_contiguous() -> None:
    known = {key for key, _title in NAVIGATION_GROUPS}
    seen: list[str] = []
    for section in default_navigation_sections():
        assert section.group in known
        if not seen or seen[-1] != section.group:
            assert section.group not in seen, "группа разорвана"
            seen.append(section.group)
    assert default_navigation_sections()[0].key == "home"


def test_verdict_code_is_read_from_json_report(tmp_path: Path) -> None:
    from zap2_gui.widgets.net_verdict_panel import verdict_code_from_report

    report = tmp_path / "r.json"
    report.write_text(json.dumps({"verdict": {"code": "IP_BLOCK"}}), encoding="utf-8")
    assert verdict_code_from_report(report) == "IP_BLOCK"
    assert verdict_code_from_report(tmp_path / "missing.json") == ""


def test_main_window_group_headers_are_not_selectable(monkeypatch) -> None:
    pytest.importorskip("PyQt6")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QApplication, QPushButton
    from zap2_gui.windows.main_window import create_main_window

    app = QApplication.instance() or QApplication([])
    window = create_main_window(ROOT)
    nav = window.navigation_list
    sections = default_navigation_sections()
    headers = [nav.item(row) for row in range(nav.count()) if nav.item(row).data(Qt.ItemDataRole.UserRole) is None]
    assert [h.text() for h in headers] == ["СРЕДСТВА", "СИСТЕМА"]
    assert all(not (h.flags() & Qt.ItemFlag.ItemIsSelectable) for h in headers)
    assert nav.count() == len(sections) + len(headers)
    for section in sections:
        assert window.focus_discovery_target(section.key, None)
        assert window.content_stack.currentWidget().objectName() in {f"page-{section.key}", "overviewScrollArea"}
        assert nav.currentItem().data(Qt.ItemDataRole.UserRole) == section.key

    # Кнопка средства из вердикта ведёт на страницу через главное окно.
    window.focus_discovery_target("diagnostics", None)
    panel = window.findChild(QPushButton, "blockcheckNetVerdictButton").parentWidget()
    panel.show_remedies("IP_BLOCK")
    go = window.findChild(QPushButton, "netVerdictRemedy-tunnel")
    assert go is not None
    go.click()
    assert nav.currentItem().data(Qt.ItemDataRole.UserRole) == "tunnel"
    window.close()
    app.processEvents()
