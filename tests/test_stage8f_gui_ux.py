from __future__ import annotations

from pathlib import Path

from zap2_gui.theme import SOFT_PASTEL_STYLESHEET

ROOT = Path(__file__).resolve().parents[1]


def test_run_sh_defaults_to_gui_and_keeps_cli_passthrough() -> None:
    source = (ROOT / "run.sh").read_text(encoding="utf-8")
    assert 'set -- --gui' in source
    assert 'elif [[ "$1" == "--cli" ]]' in source
    assert 'export PYTHONPATH="$ROOT_DIR/gui' in source
    assert 'exec "$PYTHON_BIN" -m zap2_gui.app "$@"' in source
    assert "sudo -A" not in source


def test_run_sh_prefers_project_virtual_environment() -> None:
    source = (ROOT / "run.sh").read_text(encoding="utf-8")
    selector = (ROOT / "meta_tools/python_runtime.sh").read_text(encoding="utf-8")
    assert 'python_runtime.sh' in source
    assert 'zap2_pick_python' in source
    assert '${project_root}/.venv/bin/python' in selector
    assert 'sudo pacman -S --needed python python-pyqt6' in source


def test_soft_theme_has_navigation_cards_and_focus_state() -> None:
    assert "QFrame#navigationRail" in SOFT_PASTEL_STYLESHEET
    assert "QFrame#contentSurface" in SOFT_PASTEL_STYLESHEET
    assert "QGroupBox" in SOFT_PASTEL_STYLESHEET
    assert "QLineEdit:focus" in SOFT_PASTEL_STYLESHEET
    assert "linearGradient" not in SOFT_PASTEL_STYLESHEET


def test_main_window_remembers_geometry_and_last_page() -> None:
    source = (ROOT / "gui/zap2_gui/windows/main_window.py").read_text(encoding="utf-8")
    assert 'QSettings("The Grey Network", "z2guiflin")' in source
    assert '"ui/window-geometry"' in source
    assert '"ui/last-page-key"' in source
    assert "navigation_list.currentRowChanged.connect" in source


def test_qt_bootstrap_applies_theme_before_window_creation() -> None:
    source = (ROOT / "gui/zap2_gui/qt_app.py").read_text(encoding="utf-8")
    assert "apply_application_theme(app" in source
    assert source.index("apply_application_theme(app") < source.index("create_main_window(root)")
