from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_main_window_tab_icon_overload_order() -> None:
    source = (ROOT / "gui/zap2_gui/windows/main_window.py").read_text()
    assert "tabs.addTab(page, section_icon(section.key), section.title)" in source
    assert "tabs.addTab(section_icon(section.key), page, section.title)" not in source


def test_logs_tab_icon_overload_order() -> None:
    source = (ROOT / "gui/zap2_gui/widgets/runtime_logs.py").read_text()
    assert 'tabs.addTab(overview_output, misc_icon("logs-overview"), "Overview actions")' in source
    assert 'tabs.addTab(runtime_output, misc_icon("logs-runtime"), "Runtime")' in source
    assert 'tabs.addTab(misc_icon("logs-overview"), overview_output, "Overview actions")' not in source
    assert 'tabs.addTab(misc_icon("logs-runtime"), runtime_output, "Runtime")' not in source
