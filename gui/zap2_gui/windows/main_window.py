"""Main PyQt window factory with a compact left navigation shell."""

from __future__ import annotations

from typing import Any

from .. import PRODUCT_LABEL
from ..adapters.local_build import create_local_build_plan
from ..core_inventory import load_core_build_map, load_core_inventory_snapshot
from ..models.navigation import default_navigation_sections
from ..qt_compat import require_pyqt
from ..ui_icons import section_icon
from ..widgets.blockcheck_lab import make_blockcheck_lab_page
from ..widgets.placeholders import make_core_page, make_placeholder_page
from ..widgets.presets import make_presets_page
from ..widgets.runtime_controls import make_runtime_control_page
from ..widgets.runtime_logs import make_runtime_logs_page
from ..widgets.settings import make_settings_page
from ..widgets.tunnel import make_tunnel_page


def create_main_window(root: object | None = None) -> Any:
    """Create the main window without exposing Qt classes at import time."""

    QtCore, QtWidgets = require_pyqt()
    snapshot = load_core_inventory_snapshot(root)  # type: ignore[arg-type]
    build_map = load_core_build_map(root)  # type: ignore[arg-type]
    build_plan = create_local_build_plan(root)  # type: ignore[arg-type]
    sections = default_navigation_sections()

    class MainWindow(QtWidgets.QMainWindow):  # type: ignore[misc, valid-type]
        def __init__(self) -> None:
            super().__init__()
            self._settings = QtCore.QSettings("The Grey Network", "z2guiflin")
            self.setWindowTitle(f"Zap2 GUI Linux {PRODUCT_LABEL}")
            self.resize(1240, 840)
            self.setMinimumSize(960, 680)

            shell = QtWidgets.QWidget()
            shell.setObjectName("appShell")
            shell_layout = QtWidgets.QHBoxLayout(shell)
            shell_layout.setContentsMargins(14, 14, 14, 14)
            shell_layout.setSpacing(12)

            navigation = QtWidgets.QFrame()
            navigation.setObjectName("navigationRail")
            navigation.setFixedWidth(224)
            navigation_layout = QtWidgets.QVBoxLayout(navigation)
            navigation_layout.setContentsMargins(14, 16, 14, 14)
            navigation_layout.setSpacing(8)

            brand = QtWidgets.QLabel("z2guiflin")
            brand.setObjectName("brandTitle")
            brand_subtitle = QtWidgets.QLabel("The Grey Network")
            brand_subtitle.setObjectName("brandSubtitle")

            self.navigation_list = QtWidgets.QListWidget()
            self.navigation_list.setObjectName("navigationList")
            self.navigation_list.setIconSize(QtCore.QSize(20, 20))
            self.navigation_list.setHorizontalScrollBarPolicy(
                QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
            )

            self.content_stack = QtWidgets.QStackedWidget()
            self.content_stack.setObjectName("contentStack")

            for section in sections:
                if section.key == "overview":
                    page = make_runtime_control_page(root)
                elif section.key == "core":
                    page = make_core_page(snapshot, build_map, build_plan)
                elif section.key == "strategies":
                    page = make_presets_page(root)
                elif section.key == "diagnostics":
                    page = make_blockcheck_lab_page(root)
                elif section.key == "tunnel":
                    page = make_tunnel_page(root)
                elif section.key == "settings":
                    page = make_settings_page(self._settings)
                elif section.key == "logs":
                    page = make_runtime_logs_page(root)
                else:
                    page = make_placeholder_page(section)

                page.setObjectName(f"page-{section.key}")
                self.content_stack.addWidget(page)

                item = QtWidgets.QListWidgetItem(section_icon(section.key), section.title)
                item.setData(QtCore.Qt.ItemDataRole.UserRole, section.key)
                item.setToolTip(section.purpose)
                self.navigation_list.addItem(item)

            safety_hint = QtWidgets.QLabel(
                "Plan/status безопасны. Изменения системы требуют отдельного подтверждения."
            )
            safety_hint.setObjectName("navigationHint")
            safety_hint.setWordWrap(True)

            navigation_layout.addWidget(brand)
            navigation_layout.addWidget(brand_subtitle)
            navigation_layout.addSpacing(8)
            navigation_layout.addWidget(self.navigation_list, 1)
            navigation_layout.addWidget(safety_hint)

            content_surface = QtWidgets.QFrame()
            content_surface.setObjectName("contentSurface")
            content_layout = QtWidgets.QVBoxLayout(content_surface)
            content_layout.setContentsMargins(18, 16, 18, 18)
            content_layout.setSpacing(10)

            self.page_subtitle = QtWidgets.QLabel()
            self.page_subtitle.setObjectName("pageSubtitle")
            self.page_subtitle.setWordWrap(True)

            content_layout.addWidget(self.page_subtitle)
            content_layout.addWidget(self.content_stack, 1)

            shell_layout.addWidget(navigation)
            shell_layout.addWidget(content_surface, 1)
            self.setCentralWidget(shell)

            self.navigation_list.currentRowChanged.connect(self._select_page)
            last_row = self._settings.value("ui/last-page", 0, type=int)
            if not 0 <= last_row < len(sections):
                last_row = 0
            self.navigation_list.setCurrentRow(last_row)

            geometry = self._settings.value("ui/window-geometry")
            if geometry is not None:
                try:
                    self.restoreGeometry(geometry)
                except Exception:
                    pass

        def _select_page(self, row: int) -> None:
            if not 0 <= row < len(sections):
                return
            section = sections[row]
            self.content_stack.setCurrentIndex(row)
            self.page_subtitle.setText(section.purpose)
            self._settings.setValue("ui/last-page", row)

        def closeEvent(self, event: Any) -> None:  # noqa: N802
            self._settings.setValue("ui/window-geometry", self.saveGeometry())
            self._settings.setValue("ui/last-page", self.navigation_list.currentRow())
            self._settings.sync()
            super().closeEvent(event)

    return MainWindow()
