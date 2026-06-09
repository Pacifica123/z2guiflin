"""PyQt strategy catalog and active strategy selector."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..adapters.workspace_profiles import (
    load_workspace_catalog,
    select_workspace_strategy,
    workspace_strategies_to_text,
    workspace_strategy_to_text,
)
from ..qt_compat import require_pyqt


def _strategy_item_text(strategy: Any, active_strategy_id: str) -> str:
    marker = " ✓" if strategy.strategy_id == active_strategy_id else ""
    service = getattr(strategy, "service_target_label", "not tagged")
    return f"{strategy.title}{marker}\nservice: {service}\n{strategy.strategy_id}"


def make_strategies_page(root: Path | None = None) -> Any:
    """Create a usable Strategies tab with owner-controlled selection."""

    QtCore, QtWidgets = require_pyqt()
    page = QtWidgets.QWidget()
    layout = QtWidgets.QVBoxLayout(page)
    layout.setContentsMargins(14, 14, 14, 14)
    layout.setSpacing(10)

    title = QtWidgets.QLabel("Стратегии")
    title.setObjectName("pageTitle")
    intro = QtWidgets.QLabel(
        "Здесь выбирается strategy для Default profile. Выбор только сохраняет локальный .zap2 selection; "
        "сетевые изменения появятся позже, когда вы явно построите plan, подтвердите его и запустите Default workflow. "
        "Сгенерированные из Blockcheck стратегии появляются в списке после кнопки «Создать стратегии» во вкладке Blockcheck lab."
    )
    intro.setWordWrap(True)

    status = QtWidgets.QLabel("")
    status.setObjectName("mutedText")

    splitter = QtWidgets.QSplitter()
    try:
        splitter.setOrientation(QtCore.Qt.Orientation.Horizontal)
    except Exception:  # pragma: no cover - older Qt compatibility
        splitter.setOrientation(QtCore.Qt.Horizontal)

    strategy_list = QtWidgets.QListWidget()
    strategy_list.setMinimumWidth(280)
    strategy_list.setAlternatingRowColors(True)

    details = QtWidgets.QPlainTextEdit()
    details.setReadOnly(True)
    try:
        details.setLineWrapMode(QtWidgets.QPlainTextEdit.LineWrapMode.WidgetWidth)
    except Exception:  # pragma: no cover
        pass

    splitter.addWidget(strategy_list)
    splitter.addWidget(details)
    splitter.setStretchFactor(0, 1)
    splitter.setStretchFactor(1, 2)

    buttons = QtWidgets.QHBoxLayout()
    refresh_button = QtWidgets.QPushButton("Обновить")
    select_button = QtWidgets.QPushButton("Выбрать для Default")
    catalog_button = QtWidgets.QPushButton("Сводка catalog")
    buttons.addWidget(refresh_button)
    buttons.addWidget(select_button)
    buttons.addWidget(catalog_button)
    buttons.addStretch(1)

    def _user_role() -> Any:
        try:
            return QtCore.Qt.ItemDataRole.UserRole
        except Exception:  # pragma: no cover
            return QtCore.Qt.UserRole

    def _current_strategy_id() -> str:
        item = strategy_list.currentItem()
        return "" if item is None else str(item.data(_user_role()))

    def refresh(selected_strategy_id: str | None = None) -> None:
        strategy_list.clear()
        try:
            catalog = load_workspace_catalog(root)
            active_strategy_id = catalog.profile_by_id()[catalog.default_profile_id].strategy_id
            status.setText(f"Default profile: {catalog.default_profile_id}; selected strategy: {active_strategy_id}")
            for strategy in catalog.strategies:
                item = QtWidgets.QListWidgetItem(_strategy_item_text(strategy, active_strategy_id))
                item.setData(_user_role(), strategy.strategy_id)
                item.setToolTip(f"{strategy.service_target_label} — {strategy.summary}")
                strategy_list.addItem(item)
                if strategy.strategy_id == (selected_strategy_id or active_strategy_id):
                    strategy_list.setCurrentItem(item)
            if strategy_list.count() and strategy_list.currentItem() is None:
                strategy_list.setCurrentRow(0)
            show_details()
        except Exception as exc:  # pragma: no cover - GUI diagnostic path
            details.setPlainText(f"Strategies refresh: ошибка\n{exc}")
            status.setText("Статус: ошибка чтения catalog")

    def show_details() -> None:
        strategy_id = _current_strategy_id()
        if not strategy_id:
            details.setPlainText("Стратегия не выбрана")
            return
        try:
            details.setPlainText(workspace_strategy_to_text(strategy_id, root))
        except Exception as exc:  # pragma: no cover
            details.setPlainText(f"Strategy details: ошибка\n{exc}")

    def show_catalog() -> None:
        try:
            details.setPlainText(workspace_strategies_to_text(root))
        except Exception as exc:  # pragma: no cover
            details.setPlainText(f"Catalog summary: ошибка\n{exc}")

    def choose_strategy() -> None:
        strategy_id = _current_strategy_id()
        if not strategy_id:
            details.setPlainText("Нечего выбирать: strategy list пуст")
            return
        question = QtWidgets.QMessageBox.question(
            page,
            "Выбор стратегии",
            (
                f"Выбрать стратегию `{strategy_id}` для Default profile?\n\n"
                "Это только сохранит локальный selection в .zap2/strategies. "
                "Текущий runtime не запускается и firewall не меняется. "
                "После выбора заново создайте/подтвердите Default start-plan."
            ),
        )
        if question != QtWidgets.QMessageBox.StandardButton.Yes:
            details.setPlainText("Strategy selection: отменено пользователем")
            return
        try:
            result = select_workspace_strategy(root=root, strategy_id=strategy_id, profile_id="default", reason="gui-strategies-tab")
            details.setPlainText(result.to_text())
            refresh(selected_strategy_id=strategy_id)
        except Exception as exc:  # pragma: no cover
            details.setPlainText(f"Strategy selection: ошибка\n{exc}")

    strategy_list.currentItemChanged.connect(lambda _current, _previous: show_details())
    refresh_button.clicked.connect(lambda _checked=False: refresh())
    select_button.clicked.connect(lambda _checked=False: choose_strategy())
    catalog_button.clicked.connect(lambda _checked=False: show_catalog())

    layout.addWidget(title)
    layout.addWidget(intro)
    layout.addLayout(buttons)
    layout.addWidget(status)
    layout.addWidget(splitter, 1)
    refresh()
    return page
