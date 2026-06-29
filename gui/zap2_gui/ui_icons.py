"""Flat pastel icon helpers for the GUI shell."""

from __future__ import annotations

from pathlib import Path
from typing import Any

try:  # pragma: no cover - optional in CI
    from PyQt6 import QtGui
except ModuleNotFoundError:  # pragma: no cover - optional in CI
    QtGui = None  # type: ignore[assignment]


_ICON_ROOT = Path(__file__).resolve().parent / "assets" / "icons"

_SECTION_ICONS = {
    "overview": "overview.svg",
    "core": "core.svg",
    "strategies": "strategies.svg",
    "diagnostics": "diagnostics.svg",
    "tunnel": "tunnel.svg",
    "settings": "settings.svg",
    "logs": "logs.svg",
}

_MISC_ICONS = {
    "logs-overview": "logs-overview.svg",
    "logs-runtime": "logs-runtime.svg",
    "toggle-start": "toggle-start.svg",
    "toggle-stop": "toggle-stop.svg",
    "refresh": "refresh.svg",
    "probe": "probe.svg",
    "copy": "copy.svg",
    "details": "details.svg",
}


def _empty_icon() -> Any:
    if QtGui is None:
        return None
    return QtGui.QIcon()


def load_icon(name: str) -> Any:
    """Return a QIcon for a named asset, or an empty icon if absent."""

    if QtGui is None:
        return None
    path = _ICON_ROOT / name
    if not path.exists():
        return QtGui.QIcon()
    return QtGui.QIcon(str(path))


def section_icon(section_key: str) -> Any:
    filename = _SECTION_ICONS.get(section_key)
    return load_icon(filename) if filename else _empty_icon()


def misc_icon(icon_key: str) -> Any:
    filename = _MISC_ICONS.get(icon_key)
    return load_icon(filename) if filename else _empty_icon()


__all__ = ["section_icon", "misc_icon", "load_icon"]
