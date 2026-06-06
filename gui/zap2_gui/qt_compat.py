"""Optional PyQt compatibility layer for headless-safe imports."""

from __future__ import annotations

from typing import Any

try:  # pragma: no cover - PyQt is intentionally optional in CI/devctl checks.
    from PyQt6 import QtCore, QtWidgets
except ModuleNotFoundError:  # pragma: no cover - exercised implicitly by importability tests.
    QtCore = None  # type: ignore[assignment]
    QtWidgets = None  # type: ignore[assignment]


class PyQtUnavailableError(RuntimeError):
    """Raised when the user asks to launch GUI without installed PyQt6."""


def is_pyqt_available() -> bool:
    return QtCore is not None and QtWidgets is not None


def require_pyqt() -> tuple[Any, Any]:
    if not is_pyqt_available():
        raise PyQtUnavailableError(
            "PyQt6 не установлен. Для локального запуска GUI установите зависимость "
            "проекта, например через extra 'gui', и повторите запуск с --gui."
        )
    return QtCore, QtWidgets
