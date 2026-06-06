"""PyQt application bootstrap for the v0.3-alpha Stage 5 shell."""

from __future__ import annotations

import sys
from pathlib import Path

from .qt_compat import require_pyqt
from .windows.main_window import create_main_window


def run_gui(argv: list[str] | None = None, root: Path | None = None) -> int:
    """Run the PyQt shell locally."""

    _QtCore, QtWidgets = require_pyqt()
    app = QtWidgets.QApplication(argv or sys.argv)
    window = create_main_window(root)
    window.show()
    return int(app.exec())
