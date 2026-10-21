"""Main PyQt window factory with a compact left navigation shell."""

from __future__ import annotations

from typing import Any

from pathlib import Path
from ..project_paths import discover_layout
from ..widgets.discovery_palette import make_discovery_palette
from ..widgets.health_panel import make_health_panel
from .. import PRODUCT_LABEL
from ..adapters.local_build import create_local_build_plan
from ..core_inventory import load_core_build_map, load_core_inventory_snapshot
from ..models.navigation import default_navigation_sections, navigation_group_title
from ..qt_compat import require_pyqt
from ..ui_icons import section_icon
from ..widgets.blockcheck_lab import make_blockcheck_lab_page
from ..widgets.placeholders import make_core_page, make_placeholder_page
from ..widgets.presets import make_presets_page
from ..widgets.runtime_controls import make_runtime_control_page
from ..widgets.runtime_logs import make_runtime_logs_page
from ..widgets.settings import make_settings_page
from ..widgets.tunnel import make_tunnel_page
from ..theme_profiles import theme_profile_from_settings


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
            navigation.setFixedWidth(theme_profile_from_settings(self._settings).navigation_width_px)
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

            self._row_to_index: dict[int, int] = {}
            self._key_to_row: dict[str, int] = {}
            current_group: str | None = None
            for index, section in enumerate(sections):
                if section.group != current_group:
                    current_group = section.group
                    group_title = navigation_group_title(section.group)
                    if group_title:
                        header = QtWidgets.QListWidgetItem(group_title.upper())
                        header.setFlags(QtCore.Qt.ItemFlag.NoItemFlags)
                        header_font = header.font()
                        header_font.setPointSizeF(max(7.0, header_font.pointSizeF() * 0.8))
                        header_font.setBold(True)
                        header.setFont(header_font)
                        header.setSizeHint(QtCore.QSize(0, 26))
                        self.navigation_list.addItem(header)

                if section.key == "overview":
                    page = make_runtime_control_page(root)
                elif section.key == "core":
                    page = make_core_page(snapshot, build_map, build_plan)
                elif section.key == "strategies":
                    page = make_presets_page(root, self._settings)
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

                if section.key == "overview":
                    from ..models.error_envelope import error_envelope
                    message = page.findChild(QtWidgets.QLabel, "launchIssueMessage")
                    if message is not None:
                        def update_issue_help(label=message, issue_page=page):
                            code_label = issue_page.findChild(QtWidgets.QLabel, "launchIssueCode")
                            label.setToolTip(error_envelope(code_label.text(),label.text()).text())
                        message.installEventFilter(self)
                        self._update_issue_help = update_issue_help
                page.setObjectName(f"page-{section.key}")
                if section.key == "overview":
                    overview_scroll = QtWidgets.QScrollArea()
                    overview_scroll.setObjectName("overviewScrollArea")
                    overview_scroll.setWidgetResizable(True)
                    overview_scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
                    overview_scroll.setWidget(page)
                    overview_scroll.refresh_runtime_state = page.refresh_runtime_state
                    self.content_stack.addWidget(overview_scroll)
                else:
                    self.content_stack.addWidget(page)

                item = QtWidgets.QListWidgetItem(section_icon(section.key), section.title)
                item.setData(QtCore.Qt.ItemDataRole.UserRole, section.key)
                item.setToolTip(section.purpose)
                self.navigation_list.addItem(item)
                row = self.navigation_list.count() - 1
                self._row_to_index[row] = index
                self._key_to_row[section.key] = row

            safety_hint = QtWidgets.QLabel(
                "Plan/status безопасны. Изменения системы требуют отдельного подтверждения."
            )
            safety_hint.setObjectName("navigationHint")
            safety_hint.setWordWrap(True)

            discovery_button = QtWidgets.QPushButton("Найти / справка · Ctrl+K")
            discovery_button.setObjectName("globalDiscoveryButton")
            from PyQt6.QtGui import QShortcut, QKeySequence
            self.discovery_palette = make_discovery_palette(self, discover_layout(root).root, self.focus_discovery_target)
            discovery_button.clicked.connect(self.open_discovery)
            self.discovery_shortcut = QShortcut(QKeySequence("Ctrl+K"), self)
            self.discovery_shortcut.activated.connect(self.open_discovery)
            about_button=QtWidgets.QPushButton("О программе / идентификаторы")
            about_button.setObjectName("productIdentityButton")
            about_button.clicked.connect(self.show_product_identity)
            navigation_layout.addWidget(about_button)
            navigation_layout.addWidget(discovery_button)
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

            self.health_panel = make_health_panel(root)
            content_layout.addWidget(self.health_panel)
            content_layout.addWidget(self.page_subtitle)
            content_layout.addWidget(self.content_stack, 1)

            shell_layout.addWidget(navigation)
            shell_layout.addWidget(content_surface, 1)
            self.setCentralWidget(shell)

            self.navigation_list.currentRowChanged.connect(self._select_page)
            last_key = str(self._settings.value("ui/last-page-key", sections[0].key) or "")
            self.navigation_list.setCurrentRow(self._key_to_row.get(last_key, self._key_to_row[sections[0].key]))

            geometry = self._settings.value("ui/window-geometry")
            if geometry is not None:
                try:
                    self.restoreGeometry(geometry)
                except Exception:
                    pass

        def show_product_identity(self):
            from ..product_identity import identity_snapshot
            import json
            dialog=QtWidgets.QDialog(self);dialog.setWindowTitle("О программе: независимые версии и ID")
            dialog.resize(720,520);layout=QtWidgets.QVBoxLayout(dialog)
            hint=QtWidgets.QLabel("Версия продукта, upstream, external core, схемы и evidence имеют разный смысл. Они не доказывают доступность сети.")
            hint.setWordWrap(True);layout.addWidget(hint)
            text=QtWidgets.QPlainTextEdit();text.setReadOnly(True)
            text.setPlainText(json.dumps(identity_snapshot(root),ensure_ascii=False,indent=2));layout.addWidget(text)
            close=QtWidgets.QPushButton("Закрыть");close.clicked.connect(dialog.accept);layout.addWidget(close)
            dialog.exec()

        def eventFilter(self, watched, event):
            if watched.objectName() == "launchIssueMessage" and event.type() == QtCore.QEvent.Type.ToolTip:
                self._update_issue_help()
            return super().eventFilter(watched,event)

        def open_discovery(self) -> None:
            self.discovery_palette.show()
            self.discovery_palette.raise_()
            self.discovery_palette.query.setFocus()

        def focus_discovery_target(self, page_key: str, object_name: str | None) -> bool:
            row = self._key_to_row.get(page_key)
            if row is None: return False
            self.navigation_list.setCurrentRow(row)
            if object_name is None: return True
            page = self.content_stack.widget(self._row_to_index[row])
            target = page.findChild(QtWidgets.QWidget, object_name)
            if target is None: return False
            target.setFocus()
            scroll = page.findChild(QtWidgets.QScrollArea)
            if scroll is not None: scroll.ensureWidgetVisible(target)
            return True

        def _select_page(self, row: int) -> None:
            index = self._row_to_index.get(row)
            if index is None:
                return
            section = sections[index]
            self.content_stack.setCurrentIndex(index)
            self.page_subtitle.setText(section.purpose)
            self._settings.setValue("ui/last-page-key", section.key)
            page = self.content_stack.currentWidget()
            refresh = getattr(page, "refresh_runtime_state", None)
            if callable(refresh):
                refresh()

        def closeEvent(self, event: Any) -> None:  # noqa: N802
            self._settings.setValue("ui/window-geometry", self.saveGeometry())
            index = self._row_to_index.get(self.navigation_list.currentRow())
            if index is not None:
                self._settings.setValue("ui/last-page-key", sections[index].key)
            self._settings.sync()
            super().closeEvent(event)

    return MainWindow()
