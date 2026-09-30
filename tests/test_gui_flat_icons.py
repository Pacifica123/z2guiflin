from pathlib import Path

from zap2_gui.models.navigation import default_navigation_sections
from zap2_gui.ui_icons import _ICON_ROOT


def test_section_icons_exist_for_all_navigation_sections() -> None:
    expected = {section.key for section in default_navigation_sections()}
    for key in expected:
        assert (_ICON_ROOT / f"{key}.svg").exists(), key


def test_misc_icons_exist_for_overview_and_logs_actions() -> None:
    for name in (
        "logs-overview.svg",
        "logs-runtime.svg",
        "toggle-start.svg",
        "toggle-stop.svg",
        "refresh.svg",
        "probe.svg",
        "copy.svg",
        "details.svg",
    ):
        assert (_ICON_ROOT / name).exists(), name


def test_flat_icons_do_not_use_pastel_background_boxes() -> None:
    for path in _ICON_ROOT.glob("*.svg"):
        source = path.read_text()
        assert 'width="20" height="20" rx="6" fill=' not in source, path.name
        assert '<circle cx="12" cy="12" r="10" fill=' not in source, path.name
        assert 'filter=' not in source, path.name
        assert 'linearGradient' not in source, path.name


def test_runtime_start_button_keeps_icon_and_readable_action_caption() -> None:
    source = (Path(__file__).resolve().parents[1] / "gui/zap2_gui/widgets/runtime_controls.py").read_text()
    assert 'toggle_button.setText("■" if started else "▶")' not in source
    assert 'toggle_button.setText("▶")' not in source
    assert 'toggle_button.setText("Остановить" if all_selected_running else "Запустить")' in source
    assert 'toggle_button.setIcon(' in source
