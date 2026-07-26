"""PyQt каталог: пресет -> упорядоченные traffic-профили -> детали."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..adapters.presets import (
    load_preset_catalog,
    preset_catalog_to_text,
    select_preset,
    traffic_profile_to_text,
)
from ..qt_compat import require_pyqt


_PROFILE_COLUMNS = ("#", "Профиль", "Фильтр", "Стратегия", "Range", "Direction")


def _preset_item_text(entry: Any, selected_preset_id: str) -> str:
    preset = entry.preset
    marker = " ✓" if preset.preset_id == selected_preset_id else ""
    return (
        f"{preset.title}{marker}\n"
        f"профилей: {len(preset.profiles)} · действий: {preset.action_count}\n"
        f"{preset.preset_id}"
    )


def make_presets_page(root: Path | None = None) -> Any:
    QtCore, QtWidgets = require_pyqt()
    page = QtWidgets.QWidget()
    layout = QtWidgets.QVBoxLayout(page)
    layout.setContentsMargins(14, 14, 14, 14)
    layout.setSpacing(10)

    title = QtWidgets.QLabel("Пресеты")
    title.setObjectName("pageTitle")
    intro = QtWidgets.QLabel(
        "Пресет — это полный набор параметров nfqws2. Внутри него профили идут сверху вниз: "
        "при первом совпадении filter выбирается один профиль, а остальные уже не проверяются. "
        "Выбор пресета только сохраняет локальное состояние; запуск остаётся за plan и confirmation."
    )
    intro.setWordWrap(True)

    status = QtWidgets.QLabel("")
    status.setObjectName("mutedText")

    buttons = QtWidgets.QHBoxLayout()
    refresh_button = QtWidgets.QPushButton("Обновить")
    select_button = QtWidgets.QPushButton("Выбрать пресет")
    catalog_button = QtWidgets.QPushButton("Сводка")
    buttons.addWidget(refresh_button)
    buttons.addWidget(select_button)
    buttons.addWidget(catalog_button)
    buttons.addStretch(1)

    outer_splitter = QtWidgets.QSplitter()
    try:
        outer_splitter.setOrientation(QtCore.Qt.Orientation.Horizontal)
    except Exception:  # pragma: no cover
        outer_splitter.setOrientation(QtCore.Qt.Horizontal)

    preset_list = QtWidgets.QListWidget()
    preset_list.setMinimumWidth(300)
    preset_list.setAlternatingRowColors(True)

    right = QtWidgets.QWidget()
    right_layout = QtWidgets.QVBoxLayout(right)
    right_layout.setContentsMargins(0, 0, 0, 0)
    right_layout.setSpacing(8)

    priority = QtWidgets.QLabel(
        "Порядок профилей — это приоритет. Строка выше выигрывает при пересечении фильтров."
    )
    priority.setWordWrap(True)

    profile_table = QtWidgets.QTableWidget(0, len(_PROFILE_COLUMNS))
    profile_table.setHorizontalHeaderLabels(_PROFILE_COLUMNS)
    profile_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
    profile_table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
    profile_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
    profile_table.setAlternatingRowColors(True)
    profile_table.verticalHeader().setVisible(False)
    header = profile_table.horizontalHeader()
    header.setStretchLastSection(False)
    for index in range(len(_PROFILE_COLUMNS)):
        mode = QtWidgets.QHeaderView.ResizeMode.ResizeToContents
        if index in {1, 2, 3}:
            mode = QtWidgets.QHeaderView.ResizeMode.Stretch
        header.setSectionResizeMode(index, mode)

    details = QtWidgets.QPlainTextEdit()
    details.setReadOnly(True)
    try:
        details.setLineWrapMode(QtWidgets.QPlainTextEdit.LineWrapMode.WidgetWidth)
    except Exception:  # pragma: no cover
        pass

    right_layout.addWidget(priority)
    right_layout.addWidget(profile_table, 2)
    right_layout.addWidget(details, 1)
    outer_splitter.addWidget(preset_list)
    outer_splitter.addWidget(right)
    outer_splitter.setStretchFactor(0, 1)
    outer_splitter.setStretchFactor(1, 3)

    state: dict[str, Any] = {"catalog": None, "entry": None}

    def _user_role() -> Any:
        try:
            return QtCore.Qt.ItemDataRole.UserRole
        except Exception:  # pragma: no cover
            return QtCore.Qt.UserRole

    def _current_preset_id() -> str:
        item = preset_list.currentItem()
        return "" if item is None else str(item.data(_user_role()))

    def _current_profile_id() -> str:
        row = profile_table.currentRow()
        if row < 0:
            return ""
        item = profile_table.item(row, 0)
        return "" if item is None else str(item.data(_user_role()))

    def _fill_profiles() -> None:
        catalog = state.get("catalog")
        if catalog is None:
            return
        preset_id = _current_preset_id()
        entry = catalog.by_id().get(preset_id)
        state["entry"] = entry
        profile_table.setRowCount(0)
        if entry is None:
            details.setPlainText("Пресет не выбран")
            return
        for profile in entry.preset.profiles:
            row = profile_table.rowCount()
            profile_table.insertRow(row)
            values = (
                str(profile.index + 1),
                profile.name,
                profile.traffic_filter.summary,
                profile.strategy_label,
                profile.range_label,
                profile.direction_label,
            )
            for column, value in enumerate(values):
                item = QtWidgets.QTableWidgetItem(value)
                if column == 0:
                    item.setData(_user_role(), profile.profile_id)
                profile_table.setItem(row, column, item)
        if entry.preset.profiles:
            profile_table.selectRow(0)
            _show_profile_details()
        else:
            details.setPlainText(
                f"{entry.preset.title}\n\nTraffic-профилей нет. Пресет содержит только глобальные параметры "
                "или является read-only сценарием."
            )

    def _show_profile_details() -> None:
        entry = state.get("entry")
        if entry is None:
            return
        profile_id = _current_profile_id()
        profiles = {profile.profile_id: profile for profile in entry.preset.profiles}
        profile = profiles.get(profile_id)
        if profile is None:
            return
        details.setPlainText(traffic_profile_to_text(entry.preset, profile))

    def refresh(selected_preset_id: str | None = None) -> None:
        preset_list.clear()
        profile_table.setRowCount(0)
        try:
            catalog = load_preset_catalog(root)
            state["catalog"] = catalog
            active = selected_preset_id or catalog.selected_preset_id
            for entry in catalog.entries:
                item = QtWidgets.QListWidgetItem(_preset_item_text(entry, catalog.selected_preset_id))
                item.setData(_user_role(), entry.preset.preset_id)
                preset_list.addItem(item)
                if entry.preset.preset_id == active:
                    preset_list.setCurrentItem(item)
            if preset_list.count() and preset_list.currentItem() is None:
                preset_list.setCurrentRow(0)
            status.setText(
                f"Выбран: {catalog.selected_preset_id}; пресетов: {len(catalog.entries)}; "
                f"профилей: {catalog.profile_count}"
            )
            _fill_profiles()
        except Exception as exc:  # pragma: no cover - GUI diagnostic path
            details.setPlainText(f"Preset catalog: ошибка\n{exc}")
            status.setText("Статус: ошибка чтения каталога")

    def choose_preset() -> None:
        preset_id = _current_preset_id()
        if not preset_id:
            details.setPlainText("Нечего выбирать: каталог пуст")
            return
        question = QtWidgets.QMessageBox.question(
            page,
            "Выбор пресета",
            (
                f"Выбрать пресет `{preset_id}` для Default workspace?\n\n"
                "Это только сохранит selection в .zap2. Runtime и firewall сейчас не меняются. "
                "После выбора нужно заново создать и подтвердить Default start-plan."
            ),
        )
        if question != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        try:
            result = select_preset(preset_id, root=root, workspace_id="default", reason="gui-presets-tab")
            details.setPlainText(result.to_text().replace("Strategy", "Preset").replace("strategy", "preset"))
            refresh(selected_preset_id=preset_id)
        except Exception as exc:  # pragma: no cover
            details.setPlainText(f"Preset selection: ошибка\n{exc}")

    preset_list.currentItemChanged.connect(lambda _current, _previous: _fill_profiles())
    profile_table.itemSelectionChanged.connect(_show_profile_details)
    refresh_button.clicked.connect(lambda _checked=False: refresh())
    select_button.clicked.connect(lambda _checked=False: choose_preset())
    catalog_button.clicked.connect(lambda _checked=False: details.setPlainText(preset_catalog_to_text(root)))

    layout.addWidget(title)
    layout.addWidget(intro)
    layout.addLayout(buttons)
    layout.addWidget(status)
    layout.addWidget(outer_splitter, 1)
    refresh()
    return page
