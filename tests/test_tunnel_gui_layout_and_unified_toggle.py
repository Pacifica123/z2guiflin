from __future__ import annotations

from pathlib import Path

from zap2_gui.adapters.discord_tunnel import (
    select_tunnel_connection,
    tunnel_connection_import_vless_to_text,
    tunnel_connections_table_rows,
)

SAMPLE_A = (
    "vless://11111111-2222-4333-8444-555555555555@example-a.net:8080"
    "?security=none&encryption=none&type=tcp&host=www.example.org&headerType=http#SampleA"
)
SAMPLE_B = (
    "vless://aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee@example-b.net:443"
    "?security=tls&encryption=none&type=ws&host=cdn.example.org&path=%2Fws#SampleB"
)


def test_tunnel_connections_table_rows_are_redacted_and_active(tmp_path: Path) -> None:
    tunnel_connection_import_vless_to_text(SAMPLE_A, root=tmp_path)
    tunnel_connection_import_vless_to_text(SAMPLE_B, root=tmp_path)
    rows = tunnel_connections_table_rows(root=tmp_path)

    assert len(rows) == 2
    assert sum(1 for row in rows if row["active"] == "yes") == 1
    assert any(row["remarks"] == "SampleA" for row in rows)
    assert any(row["remarks"] == "SampleB" for row in rows)
    assert "11111111-2222" not in str(rows)
    assert "aaaaaaaa-bbbb" not in str(rows)
    assert "example-a.net" not in str(rows)
    assert "example-b.net" not in str(rows)

    first_id = rows[0]["connectionId"]
    select_tunnel_connection(first_id, root=tmp_path)
    rows_after = tunnel_connections_table_rows(root=tmp_path)
    assert next(row for row in rows_after if row["connectionId"] == first_id)["active"] == "yes"


def test_tunnel_widget_uses_tabs_and_no_guided_cli_hint() -> None:
    source = (Path(__file__).resolve().parents[1] / "gui/zap2_gui/widgets/tunnel.py").read_text()
    assert "controls_tabs = QtWidgets.QTabWidget()" in source
    assert 'controls_tabs.addTab(profiles_page, "Профили VLESS")' in source
    assert 'controls_tabs.addTab(core_page, "Tunnel core")' in source
    assert 'controls_tabs.addTab(route_page, "Discord через SOCKS")' in source
    assert "Guided CLI пример" not in source
    assert "actions_box = QtWidgets.QGroupBox" not in source


def test_overview_main_toggle_uses_launch_composer_selection() -> None:
    source = (Path(__file__).resolve().parents[1] / "gui/zap2_gui/widgets/runtime_controls.py").read_text()
    assert "selected_components_all_running()" in source
    assert "launch_composer_start_to_text(" in source
    assert "launch_composer_stop_to_text(" in source
    assert "gui_toggle_default_workflow(root=root)" not in source
    assert "Всё запущено" in source
