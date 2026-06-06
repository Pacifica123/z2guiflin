"""PyQt placeholder widgets for the first navigation shell."""

from __future__ import annotations

from typing import Any

from ..core_inventory import CoreBuildMap, CoreInventorySnapshot
from ..models.navigation import NavigationSection
from ..qt_compat import require_pyqt


def make_placeholder_page(section: NavigationSection) -> Any:
    """Create a simple read-only placeholder page for a navigation section."""

    _QtCore, QtWidgets = require_pyqt()
    page = QtWidgets.QWidget()
    layout = QtWidgets.QVBoxLayout(page)

    title = QtWidgets.QLabel(section.title)
    title.setObjectName("pageTitle")
    purpose = QtWidgets.QLabel(section.purpose)
    purpose.setWordWrap(True)
    state = QtWidgets.QLabel(f"Состояние: {section.ready_state}")
    state.setWordWrap(True)

    layout.addWidget(title)
    layout.addWidget(purpose)
    layout.addWidget(state)
    layout.addStretch(1)
    return page


def make_core_page(snapshot: CoreInventorySnapshot, build_map: CoreBuildMap) -> Any:
    """Create the first inventory-backed Core tab."""

    _QtCore, QtWidgets = require_pyqt()
    page = QtWidgets.QWidget()
    layout = QtWidgets.QVBoxLayout(page)

    title = QtWidgets.QLabel("Ядро")
    title.setObjectName("pageTitle")
    summary = QtWidgets.QLabel(
        "\n".join(
            [
                f"Upstream: {snapshot.upstream_name}",
                f"Vendored files: {snapshot.vendor_file_count}",
                f"Build units: {', '.join(unit.name for unit in build_map.units)}",
                "Автоматические проверки не запускают make/sudo.",
            ]
        )
    )
    summary.setWordWrap(True)

    layout.addWidget(title)
    layout.addWidget(summary)
    layout.addStretch(1)
    return page
