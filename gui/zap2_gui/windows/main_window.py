"""Main PyQt window factory for the Stage 5 GUI shell."""

from __future__ import annotations

from typing import Any

from .. import PRODUCT_LABEL
from ..core_inventory import load_core_build_map, load_core_inventory_snapshot
from ..models.navigation import default_navigation_sections
from ..qt_compat import require_pyqt
from ..widgets.placeholders import make_core_page, make_placeholder_page


def create_main_window(root: object | None = None) -> Any:
    """Create the main window without exposing Qt classes at import time."""

    _QtCore, QtWidgets = require_pyqt()
    snapshot = load_core_inventory_snapshot(root)  # type: ignore[arg-type]
    build_map = load_core_build_map(root)  # type: ignore[arg-type]
    sections = default_navigation_sections()

    class MainWindow(QtWidgets.QMainWindow):  # type: ignore[misc, valid-type]
        def __init__(self) -> None:
            super().__init__()
            self.setWindowTitle(f"Zap2 GUI Linux {PRODUCT_LABEL}")
            self.resize(1120, 720)

            tabs = QtWidgets.QTabWidget()
            tabs.setDocumentMode(True)
            for section in sections:
                if section.key == "core":
                    page = make_core_page(snapshot, build_map)
                else:
                    page = make_placeholder_page(section)
                tabs.addTab(page, section.title)
            self.setCentralWidget(tabs)

    return MainWindow()
