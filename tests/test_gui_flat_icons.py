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
