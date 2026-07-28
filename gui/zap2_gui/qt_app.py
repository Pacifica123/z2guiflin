"""PyQt application bootstrap for the local GUI shell."""

from __future__ import annotations

import sys
from pathlib import Path

from . import PRODUCT_LABEL
from .qt_compat import require_pyqt
from .theme import apply_soft_pastel_theme
from .ui_icons import section_icon
from .windows.main_window import create_main_window


def run_gui(argv: list[str] | None = None, root: Path | None = None) -> int:
    """Run the PyQt shell locally."""

    _QtCore, QtWidgets = require_pyqt()
    app = QtWidgets.QApplication(argv or sys.argv)
    app.setApplicationName("z2guiflin")
    app.setApplicationDisplayName(f"Zap2 GUI Linux {PRODUCT_LABEL}")
    app.setOrganizationName("The Grey Network")
    apply_soft_pastel_theme(app)

    icon = section_icon("overview")
    if icon is not None:
        try:
            app.setWindowIcon(icon)
        except Exception:
            pass

    window = create_main_window(root)
    window.show()
    return int(app.exec())
