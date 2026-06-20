"""Main PyQt window factory for the Stage 5+ GUI shell."""

from __future__ import annotations

from typing import Any

from .. import PRODUCT_LABEL
from ..adapters.local_build import create_local_build_plan
from ..adapters.workspace_profiles import load_workspace_catalog
from ..core_inventory import load_core_build_map, load_core_inventory_snapshot
from ..models.navigation import default_navigation_sections
from ..qt_compat import require_pyqt
from ..widgets.blockcheck_lab import make_blockcheck_lab_page
from ..widgets.placeholders import make_core_page, make_placeholder_page
from ..widgets.strategies import make_strategies_page
from ..widgets.runtime_controls import make_runtime_control_page
from ..widgets.runtime_logs import make_runtime_logs_page
from ..widgets.tunnel import make_tunnel_page


def create_main_window(root: object | None = None) -> Any:
    """Create the main window without exposing Qt classes at import time."""

    _QtCore, QtWidgets = require_pyqt()
    snapshot = load_core_inventory_snapshot(root)  # type: ignore[arg-type]
    build_map = load_core_build_map(root)  # type: ignore[arg-type]
    build_plan = create_local_build_plan(root)  # type: ignore[arg-type]
    workspace_catalog = load_workspace_catalog(root)  # type: ignore[arg-type]
    sections = default_navigation_sections()

    class MainWindow(QtWidgets.QMainWindow):  # type: ignore[misc, valid-type]
        def __init__(self) -> None:
            super().__init__()
            self.setWindowTitle(f"Zap2 GUI Linux {PRODUCT_LABEL}")
            self.resize(1240, 840)
            self.setMinimumSize(960, 680)

            tabs = QtWidgets.QTabWidget()
            tabs.setDocumentMode(True)
            for section in sections:
                if section.key == "overview":
                    page = make_runtime_control_page(root)
                elif section.key == "core":
                    page = make_core_page(snapshot, build_map, build_plan)
                elif section.key == "strategies":
                    page = make_strategies_page(root)
                elif section.key == "diagnostics":
                    page = make_blockcheck_lab_page(root)
                elif section.key == "tunnel":
                    page = make_tunnel_page(root)
                elif section.key == "logs":
                    page = make_runtime_logs_page(root)
                else:
                    page = make_placeholder_page(section)
                tabs.addTab(page, section.title)
            self.setCentralWidget(tabs)

    return MainWindow()
