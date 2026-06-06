"""PyQt placeholder widgets for the first navigation shell."""

from __future__ import annotations

from typing import Any

from ..adapters.local_build import LocalBuildPlan
from ..adapters.workspace_profiles import WorkspaceCatalog
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


def make_core_page(snapshot: CoreInventorySnapshot, build_map: CoreBuildMap, build_plan: LocalBuildPlan) -> Any:
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
                f"Local build target: {build_plan.target}",
                f"Expected artifacts: {', '.join(item.relative_path for item in build_plan.expected_artifacts)}",
                "Build command preview:",
                *build_plan.command_previews(),
                "Автоматические проверки не запускают make/sudo.",
            ]
        )
    )
    summary.setWordWrap(True)

    layout.addWidget(title)
    layout.addWidget(summary)
    layout.addStretch(1)
    return page


def make_strategies_page(catalog: WorkspaceCatalog) -> Any:
    """Create the first profiles-backed Strategies tab."""

    _QtCore, QtWidgets = require_pyqt()
    page = QtWidgets.QWidget()
    layout = QtWidgets.QVBoxLayout(page)

    title = QtWidgets.QLabel("Стратегии")
    title.setObjectName("pageTitle")
    lines = [
        f"Workspace profiles: {len(catalog.profiles)}",
        f"Strategies: {len(catalog.strategies)}",
        f"Default profile: {catalog.default_profile_id}",
        f"Default strategy: {catalog.default_strategy_id}",
        "",
        "Профили:",
    ]
    for profile in catalog.profiles:
        lines.append(f"- {profile.profile_id}: {profile.title} -> {profile.strategy_id}")
    lines.append("")
    lines.append("Стратегии:")
    for strategy in catalog.strategies:
        lines.append(f"- {strategy.strategy_id}: {strategy.title}; plan-only: да")
    lines.append("")
    lines.append("Stage 7 только читает эти данные и не применяет их к системе.")

    summary = QtWidgets.QLabel("\n".join(lines))
    summary.setWordWrap(True)

    layout.addWidget(title)
    layout.addWidget(summary)
    layout.addStretch(1)
    return page
