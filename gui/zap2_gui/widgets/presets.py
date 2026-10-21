"""PyQt каталог и конструктор: пресет -> ordered traffic profiles."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..adapters.preset_editor import (
    add_owner_preset_profile,
    add_owner_profile_exclusions,
    can_remove_preset,
    copy_preset_for_editing,
    create_owner_preset,
    editable_profile_from_runtime,
    is_preset_editor_managed,
    move_owner_preset_profile,
    remove_owner_preset,
    remove_owner_preset_profile,
    remove_presets,
    update_owner_preset_profile,
)
from ..adapters.preset_exclusions import (
    LOCAL_NETWORKS,
    exclusion_coverage,
    load_global_exclusions,
    normalize_exclusions,
    save_global_exclusions,
)
from ..adapters.presets import (
    load_preset_catalog,
    preset_catalog_to_text,
    select_preset,
    traffic_profile_to_text,
)
from ..adapters.preset_txt_import import analyze_txt_preset, import_txt_preset
from ..adapters.preset_hot_swap import hot_swap_preset, restart_running_preset
from ..adapters.strat_collection import load_strat_collection
from ..adapters.strat_collection_port import (
    analyze_strat_port,
    port_strat_collection_entry,
)
from ..models.preset_labels import display_title, preset_chips
from ..models.profile_overlap import SimulatedConnection, file_list_resolver, find_overlaps, simulate_first_match
from ..project_paths import discover_layout
from ..qt_compat import require_pyqt
from .preset_constructor import edit_traffic_profile_dialog


_PROFILE_COLUMNS = ("#", "Профиль", "Фильтр", "Стратегия", "Range", "Direction")
_L7_CHOICES = ("", "tls", "http", "quic", "stun", "discord", "wireguard", "dht", "unknown")

PRIORITY_TEXT = (
    "Как nfqws2 выбирает профиль: для каждого соединения профили проверяются сверху вниз, "
    "и срабатывает первый, у которого совпали все условия (протокол и порт, L7, домен, IP). "
    "Профили ниже для этого соединения уже не рассматриваются. Поэтому узкие профили "
    "(конкретные домены или адреса) ставьте выше общих. Порядок меняется перетаскиванием строки или кнопками ↑ ↓."
)


def _entry_title(entry: Any) -> str:
    return display_title(entry.preset.title, entry.metadata.source_preset, entry.metadata.service_target, entry.preset.to_runtime_args())


def _preset_item_text(entry: Any, selected_preset_id: str) -> str:
    """Текст элемента для поиска и доступности; рисует его делегат."""

    preset = entry.preset
    marker = " ✓" if preset.preset_id == selected_preset_id else ""
    managed = " · constructor" if bool((entry.metadata.source_preset or {}).get("editorManaged")) else ""
    readable = _entry_title(entry)
    original = f" ({preset.title})" if readable != preset.title else ""
    return (
        f"{readable}{marker}{original}\n"
        f"профилей: {len(preset.profiles)} · действий: {preset.action_count}{managed}\n"
        f"{preset.preset_id}"
    )


def _chip_role() -> int:
    from PyQt6 import QtCore  # type: ignore[import-not-found]

    return int(QtCore.Qt.ItemDataRole.UserRole) + 1


def _make_preset_delegate(QtCore: Any, QtGui: Any, QtWidgets: Any, role: int) -> Any:
    """Название жирным, под ним цветные метки и мелкая строка с числом профилей."""

    tones = {
        "accent": None,
        "warn": QtGui.QColor(230, 160, 40, 90),
        "error": QtGui.QColor(220, 70, 70, 100),
        "muted": None,
    }

    class PresetDelegate(QtWidgets.QStyledItemDelegate):
        def paint(self, painter: Any, option: Any, index: Any) -> None:
            data = index.data(role)
            if not isinstance(data, dict):
                super().paint(painter, option, index)
                return
            opt = QtWidgets.QStyleOptionViewItem(option)
            self.initStyleOption(opt, index)
            opt.text = ""
            style = opt.widget.style() if opt.widget is not None else QtWidgets.QApplication.style()
            style.drawControl(QtWidgets.QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget)
            painter.save()
            rect = opt.rect.adjusted(8, 6, -8, -6)
            selected = bool(opt.state & QtWidgets.QStyle.StateFlag.State_Selected)
            text_role = QtGui.QPalette.ColorRole.HighlightedText if selected else QtGui.QPalette.ColorRole.Text
            text_color = opt.palette.color(text_role)
            bold = QtGui.QFont(opt.font)
            bold.setBold(True)
            metrics = QtGui.QFontMetrics(bold)
            painter.setFont(bold)
            painter.setPen(text_color)
            painter.drawText(rect.x(), rect.y() + metrics.ascent(),
                             metrics.elidedText(str(data.get("title", "")), QtCore.Qt.TextElideMode.ElideRight, rect.width()))
            y = rect.y() + metrics.height() + 4
            small = QtGui.QFont(opt.font)
            if small.pointSizeF() > 0:
                small.setPointSizeF(max(7.0, small.pointSizeF() * 0.85))
            small_metrics = QtGui.QFontMetrics(small)
            painter.setFont(small)
            x = rect.x()
            chip_h = small_metrics.height() + 2
            for text, tone in data.get("chips", ()):
                width = small_metrics.horizontalAdvance(text) + 12
                if x + width > rect.right():
                    break
                fill = tones.get(tone)
                if fill is None:
                    fill = QtGui.QColor(opt.palette.color(QtGui.QPalette.ColorRole.Highlight if tone == "accent" else QtGui.QPalette.ColorRole.Mid))
                    fill.setAlpha(110 if tone == "accent" else 70)
                chip = QtCore.QRectF(x, y, width, chip_h)
                painter.setPen(QtCore.Qt.PenStyle.NoPen)
                painter.setBrush(fill)
                painter.drawRoundedRect(chip, chip_h / 2, chip_h / 2)
                painter.setPen(text_color)
                painter.drawText(chip, int(QtCore.Qt.AlignmentFlag.AlignCenter), text)
                x += width + 4
            y += chip_h + 4
            muted = QtGui.QColor(text_color)
            muted.setAlpha(150)
            painter.setPen(muted)
            painter.drawText(rect.x(), y + small_metrics.ascent(),
                             small_metrics.elidedText(str(data.get("meta", "")), QtCore.Qt.TextElideMode.ElideRight, rect.width()))
            painter.restore()

        def sizeHint(self, option: Any, index: Any) -> Any:
            metrics = QtGui.QFontMetrics(option.font)
            return QtCore.QSize(220, int(metrics.height() * 3.3) + 18)

    return PresetDelegate()


def drop_target_index(source: int, row: int, below: bool, row_count: int) -> int:
    """Итоговая позиция строки после перетаскивания (как у pop + insert)."""

    target = row_count if row < 0 else row + (1 if below else 0)
    return target - 1 if target > source else target


def _make_profile_table(QtCore: Any, QtWidgets: Any, columns: int, on_move: Any) -> Any:
    """Таблица профилей, где строку можно перетащить: порядок = приоритет."""

    class ProfileTable(QtWidgets.QTableWidget):
        def dropEvent(self, event: Any) -> None:  # noqa: N802 - Qt API
            source = self.currentRow()
            index = self.indexAt(event.position().toPoint())
            below = self.dropIndicatorPosition() == QtWidgets.QAbstractItemView.DropIndicatorPosition.BelowItem
            final = drop_target_index(source, index.row() if index.isValid() else -1, below, self.rowCount())
            # Сам Qt строки не двигает: порядок меняет файл пресета, таблица перечитывается.
            event.setDropAction(QtCore.Qt.DropAction.IgnoreAction)
            event.ignore()
            if source >= 0 and final != source and 0 <= final < self.rowCount():
                QtCore.QTimer.singleShot(0, lambda: on_move(source, final))

    table = ProfileTable(0, columns)
    table.setDragDropMode(QtWidgets.QAbstractItemView.DragDropMode.InternalMove)
    table.setDragDropOverwriteMode(False)
    table.setDropIndicatorShown(True)
    table.setDefaultDropAction(QtCore.Qt.DropAction.MoveAction)
    table.setDragEnabled(False)
    return table


def make_presets_page(root: Path | None = None, settings: Any | None = None) -> Any:
    QtCore, QtWidgets = require_pyqt()
    from PyQt6 import QtGui  # type: ignore[import-not-found]
    settings = settings or QtCore.QSettings("The Grey Network", "z2guiflin")
    page = QtWidgets.QWidget()
    layout = QtWidgets.QVBoxLayout(page)
    layout.setContentsMargins(12, 12, 8, 12)
    layout.setSpacing(10)

    title = QtWidgets.QLabel("Пресеты")
    title.setObjectName("pageTitle")
    intro = QtWidgets.QLabel(
        "Пресет — полный набор параметров nfqws2. Клик открывает его профили, двойной клик или «Применить пресет» включает его."
    )
    intro.setToolTip(
        "strat_collection встроен как legacy-каталог: однозначно совместимые записи можно безопасно портировать в nfqws2, "
        "остальные остаются read-only."
    )
    intro.setWordWrap(True)

    status = QtWidgets.QLabel("")
    status.setObjectName("mutedText")
    status.setWordWrap(True)

    search_row = QtWidgets.QHBoxLayout()
    search_label = QtWidgets.QLabel("Поиск")
    search_edit = QtWidgets.QLineEdit()
    search_edit.setPlaceholderText("Название, id, provider, hostlist, режим…   Ctrl+F")
    search_clear = QtWidgets.QToolButton()
    search_clear.setText("×")
    search_clear.setToolTip("Очистить поиск")
    search_row.addWidget(search_label)
    search_row.addWidget(search_edit, 1)
    search_row.addWidget(search_clear)

    # Общие действия страницы: применить выбранное (пресет или strat_collection), перечитать, сводка.
    buttons = QtWidgets.QHBoxLayout()
    select_button = QtWidgets.QPushButton("Применить пресет")
    select_button.setToolTip("Выбрать пресет и применить его через hot-swap")
    refresh_button = QtWidgets.QPushButton("Обновить")
    catalog_button = QtWidgets.QPushButton("Сводка")
    buttons.addWidget(select_button)
    buttons.addWidget(refresh_button)
    buttons.addWidget(catalog_button)
    exclusions_button = QtWidgets.QPushButton("Общие исключения…")
    exclusions_button.setToolTip("Домены и адреса, которые не трогает ни один пресет: банк, госуслуги, локальная сеть")
    buttons.addWidget(exclusions_button)
    buttons.addSpacing(12)
    buttons.addWidget(status, 1)

    # Панель пресетов: список и действия над пресетом целиком.
    new_preset_button = QtWidgets.QPushButton("+ Пресет")
    import_preset_button = QtWidgets.QPushButton("Импорт .txt")
    copy_preset_button = QtWidgets.QPushButton("Копия для правки")
    copy_preset_button.setToolTip("Создать свою редактируемую копию; исходный пресет не меняется")
    remove_preset_button = QtWidgets.QPushButton("Удалить пресет")
    remove_preset_button.setToolTip(
        "Удалить выделенные свои пресеты и найденные Blockcheck. Несколько — Ctrl/Shift+клик или правая кнопка → «Выделить все Blockcheck»"
    )

    preset_box = QtWidgets.QGroupBox("Пресеты")
    preset_box_layout = QtWidgets.QVBoxLayout(preset_box)
    preset_list = QtWidgets.QListWidget()
    preset_list.setMinimumWidth(200)
    preset_list.setAlternatingRowColors(True)
    preset_list.setItemDelegate(_make_preset_delegate(QtCore, QtGui, QtWidgets, _chip_role()))
    preset_list.setToolTip("Клик — посмотреть профили, двойной клик — применить")
    preset_list.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
    preset_list.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
    preset_actions = QtWidgets.QGridLayout()
    preset_actions.addWidget(new_preset_button, 0, 0)
    preset_actions.addWidget(import_preset_button, 0, 1)
    preset_actions.addWidget(copy_preset_button, 1, 0)
    preset_actions.addWidget(remove_preset_button, 1, 1)
    preset_box_layout.addWidget(preset_list, 1)
    preset_box_layout.addLayout(preset_actions)

    # Панель профилей выбранного пресета: порядок, правка, проверка пересечений.
    new_profile_button = QtWidgets.QPushButton("+ Профиль")
    edit_profile_button = QtWidgets.QPushButton("Изменить")
    remove_profile_button = QtWidgets.QPushButton("Удалить")
    remove_profile_button.setToolTip("Удалить профиль из пресета")
    move_up_button = QtWidgets.QPushButton("↑")
    move_down_button = QtWidgets.QPushButton("↓")
    move_up_button.setToolTip("Поднять профиль: он будет проверяться раньше")
    move_down_button.setToolTip("Опустить профиль")
    simulate_open_button = QtWidgets.QPushButton("Кто сработает первым?")
    simulate_open_button.setToolTip("Указать соединение (протокол, порт, домен) и увидеть, какой профиль его заберёт")
    profile_actions = QtWidgets.QGridLayout()
    for column, button in enumerate((new_profile_button, edit_profile_button, remove_profile_button)):
        profile_actions.addWidget(button, 0, column)
    order_row = QtWidgets.QHBoxLayout()
    order_row.addWidget(move_up_button)
    order_row.addWidget(move_down_button)
    order_row.addWidget(simulate_open_button, 1)
    profile_actions.addLayout(order_row, 1, 0, 1, 3)
    profile_actions.setColumnStretch(3, 1)

    profile_box = QtWidgets.QGroupBox("Профили выбранного пресета")
    right_layout = QtWidgets.QVBoxLayout(profile_box)
    right_layout.setSpacing(8)

    priority = QtWidgets.QLabel(
        "Проверяются сверху вниз, срабатывает первый совпавший: узкие профили ставьте выше общих. "
        "Порядок — перетаскиванием строки или ↑ ↓."
    )
    priority.setToolTip(PRIORITY_TEXT)
    priority.setWordWrap(True)
    readonly_hint = QtWidgets.QLabel(
        "Этот пресет только для чтения (встроенный или найденный Blockcheck). "
        "Чтобы менять профили и порядок, нажмите «Копия для правки»."
    )
    readonly_hint.setObjectName("mutedText")
    readonly_hint.setWordWrap(True)
    readonly_hint.setVisible(False)

    profile_table = _make_profile_table(QtCore, QtWidgets, len(_PROFILE_COLUMNS), lambda source, final: move_profile_to(source, final))
    profile_table.setHorizontalHeaderLabels(_PROFILE_COLUMNS)
    profile_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
    profile_table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
    profile_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
    profile_table.setAlternatingRowColors(True)
    profile_table.setMinimumHeight(150)
    profile_table.verticalHeader().setVisible(False)
    header = profile_table.horizontalHeader()
    header.setStretchLastSection(False)
    for index in range(len(_PROFILE_COLUMNS)):
        mode = QtWidgets.QHeaderView.ResizeMode.ResizeToContents
        if index in {1, 2, 3}:
            mode = QtWidgets.QHeaderView.ResizeMode.Stretch
        header.setSectionResizeMode(index, mode)

    overlap_label = QtWidgets.QLabel("Пересечения профилей")
    overlap_label.setWordWrap(True)
    overlap_list = QtWidgets.QListWidget()
    overlap_list.setMaximumHeight(96)
    overlap_list.setMinimumHeight(48)
    overlap_list.setWordWrap(True)
    fix_buttons = [QtWidgets.QPushButton(""), QtWidgets.QPushButton("")]
    fix_row = QtWidgets.QVBoxLayout()  # столбиком: подписи исправлений длинные, а панель бывает узкой
    for button in fix_buttons:
        button.setVisible(False)
        fix_row.addWidget(button)

    details = QtWidgets.QPlainTextEdit()
    details.setReadOnly(True)
    try:
        details.setLineWrapMode(QtWidgets.QPlainTextEdit.LineWrapMode.WidgetWidth)
    except Exception:  # pragma: no cover
        pass

    profiles_part = QtWidgets.QWidget()
    profiles_layout = QtWidgets.QVBoxLayout(profiles_part)
    profiles_layout.setContentsMargins(0, 0, 0, 0)
    profiles_layout.addWidget(priority)
    profiles_layout.addWidget(readonly_hint)
    profiles_layout.addLayout(profile_actions)
    profiles_layout.addWidget(profile_table, 1)
    check_part = QtWidgets.QWidget()
    check_layout = QtWidgets.QVBoxLayout(check_part)
    check_layout.setContentsMargins(0, 0, 0, 0)
    check_layout.addWidget(overlap_label)
    check_layout.addWidget(overlap_list)
    check_layout.addLayout(fix_row)
    check_layout.addWidget(details, 1)
    right_splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
    right_splitter.addWidget(profiles_part)
    right_splitter.addWidget(check_part)
    right_splitter.setStretchFactor(0, 3)
    right_splitter.setStretchFactor(1, 2)
    details.setMinimumHeight(60)
    right_splitter.setChildrenCollapsible(False)
    right_layout.setContentsMargins(6, 6, 6, 6)
    right_layout.addWidget(right_splitter)

    outer_splitter = QtWidgets.QSplitter()
    try:
        outer_splitter.setOrientation(QtCore.Qt.Orientation.Horizontal)
    except Exception:  # pragma: no cover
        outer_splitter.setOrientation(QtCore.Qt.Horizontal)
    outer_splitter.addWidget(preset_box)
    outer_splitter.addWidget(profile_box)
    outer_splitter.setStretchFactor(0, 1)
    outer_splitter.setStretchFactor(1, 3)
    outer_splitter.setSizes([300, 700])

    local_tab = QtWidgets.QWidget()
    local_layout = QtWidgets.QVBoxLayout(local_tab)
    local_layout.setContentsMargins(0, 0, 0, 0)
    local_layout.addWidget(outer_splitter)

    collection_tab = QtWidgets.QWidget()
    collection_layout = QtWidgets.QVBoxLayout(collection_tab)
    collection_layout.setContentsMargins(0, 0, 0, 0)
    collection_hint = QtWidgets.QLabel(
        "Встроенный snapshot strat_collection. BAT/winws никогда не исполняются. "
        "Для стратегий, где все legacy-опции имеют однозначное соответствие в Zapret2, доступен консервативный автопорт "
        "в обычный owner-managed preset; неоднозначные варианты остаются read-only."
    )
    collection_hint.setWordWrap(True)
    collection_table = QtWidgets.QTableWidget(0, 6)
    collection_table.setHorizontalHeaderLabels(("Стратегия", "Provider", "Label", "Порты", "Режимы", "Совместимость"))
    collection_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
    collection_table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
    collection_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
    collection_table.setAlternatingRowColors(True)
    collection_table.verticalHeader().setVisible(False)
    collection_table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
    collection_table.horizontalHeader().setSectionResizeMode(4, QtWidgets.QHeaderView.ResizeMode.Stretch)
    collection_details = QtWidgets.QPlainTextEdit()
    collection_details.setReadOnly(True)
    collection_splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
    collection_splitter.addWidget(collection_table)
    collection_splitter.addWidget(collection_details)
    collection_splitter.setStretchFactor(0, 2)
    collection_splitter.setStretchFactor(1, 1)
    collection_layout.addWidget(collection_hint)
    collection_layout.addWidget(collection_splitter, 1)

    tabs = QtWidgets.QTabWidget()
    tabs.addTab(local_tab, "Zapret2 пресеты")
    tabs.addTab(collection_tab, "strat_collection")

    state: dict[str, Any] = {
        "catalog": None,
        "entry": None,
        "managed": False,
        "busy": False,
        "strat": None,
        "strat_rows": [],
        "strat_selected_id": "",
        "strat_plans": {},
        "overlaps": {},
        "resolver": None,
    }

    def _resolver() -> Any:
        if state.get("resolver") is None:
            try:
                state["resolver"] = file_list_resolver(discover_layout(root).root)
            except Exception:
                state["resolver"] = lambda _path: None
        return state["resolver"]

    def _overlaps_for(entry: Any) -> tuple[Any, ...]:
        cache = state.setdefault("overlaps", {})
        key = entry.preset.preset_id
        if key not in cache:
            try:
                cache[key] = find_overlaps(entry.preset, _resolver())
            except Exception:
                cache[key] = ()
        return cache[key]

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

    def _set_constructor_enabled(managed: bool) -> None:
        state["managed"] = managed
        row = profile_table.currentRow()
        has_profile = row >= 0
        has_entry = state.get("entry") is not None
        readonly_hint.setVisible(has_entry and not managed)
        copy_preset_button.setEnabled(has_entry)
        simulate_open_button.setEnabled(has_entry and bool(state["entry"].preset.profiles))
        profile_table.setDragEnabled(managed)
        for button in fix_buttons:
            button.setEnabled(managed)
        _update_remove_button()
        new_profile_button.setEnabled(managed)
        edit_profile_button.setEnabled(managed and has_profile)
        remove_profile_button.setEnabled(managed and has_profile)
        move_up_button.setEnabled(managed and has_profile and row > 0)
        move_down_button.setEnabled(managed and has_profile and row + 1 < profile_table.rowCount())

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
        _set_constructor_enabled(bool(state.get("managed")))

    def _fill_profiles(select_row: int = 0) -> None:
        catalog = state.get("catalog")
        if catalog is None:
            return
        preset_id = _current_preset_id()
        entry = catalog.by_id().get(preset_id)
        state["entry"] = entry
        profile_table.setRowCount(0)
        _set_constructor_enabled(False)
        if entry is None:
            details.setPlainText("Пресет не выбран")
            return

        managed = is_preset_editor_managed(entry.preset.preset_id, root)
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
                    item.setToolTip(f"Проверяется {profile.index + 1}-м; перетащите строку, чтобы изменить порядок")
                profile_table.setItem(row, column, item)

        dead_rows = {item.later for item in _overlaps_for(entry) if item.severity == "error"}
        for row in dead_rows:
            cell = profile_table.item(row, 1)
            if cell is not None:
                cell.setText("✖ " + cell.text())
                cell.setToolTip("Этот профиль никогда не сработает: его трафик раньше забирает профиль выше")
        _show_overlaps(entry)

        if entry.preset.profiles:
            row = max(0, min(select_row, len(entry.preset.profiles) - 1))
            profile_table.selectRow(row)
            _show_profile_details()
        else:
            kind = "constructor preset" if managed else "read-only preset"
            details.setPlainText(
                f"{entry.preset.title}\n\nTraffic-профилей нет. Это {kind}. "
                "Для constructor preset нажмите + Профиль."
            )
        _set_constructor_enabled(managed)

    def _show_overlaps(entry: Any) -> None:
        overlap_list.clear()
        items = _overlaps_for(entry)
        overlap_label.setText(
            "Пересечения профилей: не найдено" if not items else f"Пересечения профилей: {len(items)} — выберите строку, чтобы исправить"
        )
        overlap_list.setVisible(bool(items))
        for index, overlap in enumerate(items):
            row = QtWidgets.QListWidgetItem(overlap.to_text())
            row.setData(_user_role(), index)
            overlap_list.addItem(row)
        _show_fixes()

    def _current_overlap() -> Any | None:
        entry = state.get("entry")
        item = overlap_list.currentItem()
        if entry is None or item is None:
            return None
        items = _overlaps_for(entry)
        index = int(item.data(_user_role()))
        return items[index] if 0 <= index < len(items) else None

    def _show_fixes() -> None:
        overlap = _current_overlap()
        fixes = overlap.fixes if overlap is not None else ()
        managed = bool(state.get("managed"))
        for position, button in enumerate(fix_buttons):
            fix = fixes[position] if position < len(fixes) else None
            button.setVisible(fix is not None)
            if fix is not None:
                button.setText(fix.label)
                button.setEnabled(managed)
                button.setToolTip("" if managed else "Пресет только для чтения: сначала «Копия для правки»")
        if overlap is not None:
            profile_table.selectRow(overlap.later)

    def apply_fix(position: int) -> None:
        entry = state.get("entry")
        overlap = _current_overlap()
        if entry is None or overlap is None or not state.get("managed") or position >= len(overlap.fixes):
            return
        fix = overlap.fixes[position]
        try:
            if fix.kind == "move-above":
                result = move_owner_preset_profile(entry.preset.preset_id, fix.profile_index, fix.target_index, root=root)
                select_row = fix.target_index
            else:
                result = add_owner_profile_exclusions(entry.preset.preset_id, fix.profile_index, domains=fix.domains, root=root)
                select_row = fix.profile_index
            details.setPlainText(result.to_text())
            refresh(selected_preset_id=entry.preset.preset_id, select_row=select_row)
        except Exception as exc:
            QtWidgets.QMessageBox.critical(page, "Исправление не применено", str(exc))

    def open_simulator() -> None:
        entry = state.get("entry")
        if entry is None:
            return
        dialog = QtWidgets.QDialog(page)
        dialog.setWindowTitle(f"Кто сработает первым — {entry.preset.title}")
        dialog.resize(640, 460)
        box = QtWidgets.QVBoxLayout(dialog)
        hint = QtWidgets.QLabel(
            "Опишите соединение — программа пройдёт профили сверху вниз так же, как nfqws2, "
            "и покажет, какой сработает и почему остальные не подошли."
        )
        hint.setWordWrap(True)
        form = QtWidgets.QGridLayout()
        proto = QtWidgets.QComboBox()
        proto.addItem("TCP", "tcp")
        proto.addItem("UDP", "udp")
        port = QtWidgets.QSpinBox()
        port.setRange(1, 65535)
        port.setValue(443)
        l7 = QtWidgets.QComboBox()
        for value in _L7_CHOICES:
            l7.addItem(value or "L7 по порту", value)
        host = QtWidgets.QLineEdit()
        host.setPlaceholderText("домен, например www.youtube.com")
        ip = QtWidgets.QLineEdit()
        ip.setPlaceholderText("IP — необязательно")
        check = QtWidgets.QPushButton("Проверить")
        check.setDefault(True)
        form.addWidget(QtWidgets.QLabel("Протокол и порт"), 0, 0)
        form.addWidget(proto, 0, 1)
        form.addWidget(port, 0, 2)
        form.addWidget(l7, 0, 3)
        form.addWidget(QtWidgets.QLabel("Домен"), 1, 0)
        form.addWidget(host, 1, 1, 1, 3)
        form.addWidget(QtWidgets.QLabel("IP"), 2, 0)
        form.addWidget(ip, 2, 1, 1, 2)
        form.addWidget(check, 2, 3)
        output = QtWidgets.QPlainTextEdit()
        output.setReadOnly(True)
        close = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Close)
        box.addWidget(hint)
        box.addLayout(form)
        box.addWidget(output, 1)
        box.addWidget(close)

        def run() -> None:
            connection = SimulatedConnection(
                protocol=str(proto.currentData()),
                port=int(port.value()),
                host=host.text().strip(),
                ip=ip.text().strip(),
                l7=str(l7.currentData() or ""),
            )
            hosts, nets = _global_exclusions()
            result = simulate_first_match(entry.preset, connection, _resolver(), global_exclude_hosts=hosts, global_exclude_nets=nets)
            output.setPlainText(
                result.to_text()
                + "\n\nСчитается, что имя хоста и протокол уже известны. До этого (первые пакеты TCP) "
                "nfqws2 выбирает профиль без условий на домен и потом может переключиться."
            )
            if result.winner is not None:
                profile_table.selectRow(result.winner)

        check.clicked.connect(lambda _checked=False: run())
        host.returnPressed.connect(run)
        close.rejected.connect(dialog.reject)
        dialog.exec()

    def _global_exclusions() -> tuple[tuple[str, ...], tuple[str, ...]]:
        try:
            current = load_global_exclusions(discover_layout(root).root)
        except Exception:
            return (), ()
        return current.domains, current.cidrs

    def edit_global_exclusions() -> None:
        try:
            workspace = discover_layout(root).root
            current = load_global_exclusions(workspace)
        except Exception as exc:
            QtWidgets.QMessageBox.critical(page, "Общие исключения", str(exc))
            return
        dialog = QtWidgets.QDialog(page)
        dialog.setWindowTitle("Общие исключения")
        dialog.resize(620, 520)
        box = QtWidgets.QVBoxLayout(dialog)
        hint = QtWidgets.QLabel(
            "Эти домены и адреса не обрабатывает ни один профиль любого пресета: соединение идёт как без обхода. "
            "Пригодится для банков, госуслуг, рабочих VPN и локальной сети. Файлы пресетов не меняются — "
            "исключения добавляются в план запуска и видны в нём."
        )
        hint.setWordWrap(True)
        domains_edit = QtWidgets.QPlainTextEdit("\n".join(current.domains))
        domains_edit.setPlaceholderText("по одному на строку: sberbank.ru, gosuslugi.ru — поддомены включены; ^site.ru — только сам домен")
        cidrs_edit = QtWidgets.QPlainTextEdit("\n".join(current.cidrs))
        cidrs_edit.setPlaceholderText("по одному на строку: 192.168.0.0/16, 203.0.113.7")
        local_button = QtWidgets.QPushButton("+ локальные сети")
        local_button.setToolTip(", ".join(LOCAL_NETWORKS))
        note = QtWidgets.QLabel("")
        note.setObjectName("mutedText")
        note.setWordWrap(True)
        entry = state.get("entry")
        if entry is not None:
            with_domains, total = exclusion_coverage(entry.preset.to_runtime_args(), current)
            if total and with_domains < total:
                note.setText(
                    f"В «{_entry_title(entry)}» домены попадут в {with_domains} из {total} профилей: в профили без списка доменов "
                    "nfqws2 не даст их поставить без поломки первых пакетов (профиль со списком доменов не выбирается, пока "
                    "не известно имя хоста). Такие профили исключаются только по IP/CIDR."
                )
        buttons_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Save | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        box.addWidget(hint)
        box.addWidget(QtWidgets.QLabel("Домены"))
        box.addWidget(domains_edit, 1)
        cidr_row = QtWidgets.QHBoxLayout()
        cidr_row.addWidget(QtWidgets.QLabel("IP / CIDR"))
        cidr_row.addStretch(1)
        cidr_row.addWidget(local_button)
        box.addLayout(cidr_row)
        box.addWidget(cidrs_edit, 1)
        box.addWidget(note)
        box.addWidget(buttons_box)

        def add_local() -> None:
            present = set(cidrs_edit.toPlainText().split())
            extra = [item for item in LOCAL_NETWORKS if item not in present]
            text = cidrs_edit.toPlainText().rstrip()
            cidrs_edit.setPlainText((text + "\n" if text else "") + "\n".join(extra))

        def save() -> None:
            try:
                updated = normalize_exclusions(domains_edit.toPlainText().splitlines(), cidrs_edit.toPlainText().splitlines())
                save_global_exclusions(workspace, updated)
            except Exception as exc:
                QtWidgets.QMessageBox.critical(dialog, "Исключения не сохранены", str(exc))
                return
            dialog.accept()

        local_button.clicked.connect(lambda _checked=False: add_local())
        buttons_box.accepted.connect(save)
        buttons_box.rejected.connect(dialog.reject)
        if dialog.exec() != int(QtWidgets.QDialog.DialogCode.Accepted):
            return
        status.setText("Общие исключения сохранены.")
        answer = QtWidgets.QMessageBox.question(
            page,
            "Общие исключения",
            "Исключения сохранены и войдут в следующий план запуска. Если Default сейчас работает, перезапустить его, "
            "чтобы они подействовали сразу?",
        )
        if answer == QtWidgets.QMessageBox.StandardButton.Yes:
            try:
                _ok, text = restart_running_preset(root)
            except Exception as exc:
                text = f"Перезапуск не удался: {exc}"
            details.setPlainText(text)

    def refresh(selected_preset_id: str | None = None, select_row: int = 0) -> None:
        previous_current = _current_preset_id()
        preset_list.clear()
        profile_table.setRowCount(0)
        state["overlaps"] = {}
        state["resolver"] = None
        try:
            catalog = load_preset_catalog(root)
            state["catalog"] = catalog
            active = selected_preset_id or previous_current or catalog.selected_preset_id
            for entry in catalog.entries:
                item = QtWidgets.QListWidgetItem(_preset_item_text(entry, catalog.selected_preset_id))
                item.setData(_user_role(), entry.preset.preset_id)
                source = entry.metadata.source_preset or {}
                managed_entry = bool(source.get("editorManaged"))
                chips = preset_chips(
                    source,
                    managed=managed_entry,
                    selected=entry.preset.preset_id == catalog.selected_preset_id,
                    overlap_severities=(o.severity for o in _overlaps_for(entry)),
                )
                item.setData(_chip_role(), {
                    "title": _entry_title(entry),
                    "chips": [(chip.text, chip.tone) for chip in chips],
                    "meta": f"профилей: {len(entry.preset.profiles)} · действий: {entry.preset.action_count} · {entry.preset.preset_id}",
                })
                item.setToolTip("\n".join(chip.tooltip for chip in chips if chip.tooltip))
                preset_list.addItem(item)
                if entry.preset.preset_id == active:
                    preset_list.setCurrentItem(item)
            if preset_list.count() and preset_list.currentItem() is None:
                preset_list.setCurrentRow(0)
            status.setText(
                f"Выбран runtime preset: {catalog.selected_preset_id}; каталог: {len(catalog.entries)}; "
                f"traffic profiles: {catalog.profile_count}"
            )
            _fill_profiles(select_row)
            _apply_search()
        except Exception as exc:  # pragma: no cover - GUI diagnostic path
            details.setPlainText(f"Preset catalog: ошибка\n{exc}")
            status.setText("Статус: ошибка чтения каталога")

    def apply_current_preset() -> None:
        preset_id = _current_preset_id()
        if not preset_id or state.get("busy"):
            return
        state["busy"] = True
        page.setCursor(QtCore.Qt.CursorShape.WaitCursor)
        select_button.setEnabled(False)
        try:
            result = hot_swap_preset(preset_id, root=root, profile_id="default")
            details.setPlainText(result.to_text())
            refresh(selected_preset_id=result.selected_preset_id)
            if not result.success:
                QtWidgets.QMessageBox.warning(page, "Hot-swap завершён с ошибкой", result.message)
        except Exception as exc:
            details.setPlainText(f"Preset hot-swap: ошибка\n{exc}")
            QtWidgets.QMessageBox.critical(page, "Пресет не применён", str(exc))
        finally:
            state["busy"] = False
            page.unsetCursor()
            _update_apply_button()

    def double_click_apply(_item: Any) -> None:
        if settings.value("presets/double-click-apply", settings.value("presets/one-click-apply", True, type=bool), type=bool):
            apply_current_preset()

    def copy_preset() -> None:
        entry = state.get("entry")
        if entry is None:
            return
        title_text, ok = QtWidgets.QInputDialog.getText(
            page, "Копия для правки", "Название копии:", text=f"{entry.preset.title} (моя копия)"
        )
        if not ok:
            return
        try:
            result = copy_preset_for_editing(entry.preset.preset_id, root=root, title=str(title_text))
            details.setPlainText(result.to_text())
            refresh(selected_preset_id=result.preset_id)
        except Exception as exc:
            QtWidgets.QMessageBox.critical(page, "Копия не создана", str(exc))

    def create_preset() -> None:
        title_text, ok = QtWidgets.QInputDialog.getText(
            page,
            "Новый пресет",
            "Название, например Universal Rostelecom YT+DS:",
        )
        if not ok:
            return
        try:
            result = create_owner_preset(str(title_text), root=root)
            details.setPlainText(result.to_text())
            refresh(selected_preset_id=result.preset_id)
        except Exception as exc:
            QtWidgets.QMessageBox.critical(page, "Пресет не создан", str(exc))

    def _selected_entries() -> list[Any]:
        catalog = state.get("catalog")
        if catalog is None:
            return []
        entries = catalog.by_id()
        ids = [str(item.data(_user_role())) for item in preset_list.selectedItems()]
        return [entries[preset_id] for preset_id in ids if preset_id in entries]

    def _update_remove_button() -> None:
        removable = [entry for entry in _selected_entries() if can_remove_preset(entry)]
        remove_preset_button.setEnabled(bool(removable))
        remove_preset_button.setText("Удалить пресет" if len(removable) <= 1 else f"Удалить пресеты: {len(removable)}")

    def select_all_generated() -> None:
        catalog = state.get("catalog")
        if catalog is None:
            return
        entries = catalog.by_id()
        preset_list.clearSelection()
        for index in range(preset_list.count()):
            item = preset_list.item(index)
            entry = entries.get(str(item.data(_user_role())))
            if entry is not None and not item.isHidden() and str((entry.metadata.source_preset or {}).get("id")) == "blockcheck-generated":
                item.setSelected(True)
        _update_remove_button()

    def show_preset_menu(position: Any) -> None:
        menu = QtWidgets.QMenu(preset_list)
        select_generated = menu.addAction("Выделить все найденные Blockcheck")
        remove_selected = menu.addAction("Удалить выделенные")
        remove_selected.setEnabled(remove_preset_button.isEnabled())
        chosen = menu.exec(preset_list.viewport().mapToGlobal(position))
        if chosen is select_generated:
            select_all_generated()
        elif chosen is remove_selected:
            remove_preset()

    def remove_preset() -> None:
        selected = _selected_entries()
        removable = [entry for entry in selected if can_remove_preset(entry)]
        if not removable:
            return
        skipped = len(selected) - len(removable)
        if len(removable) == 1:
            entry = removable[0]
            text = (
                f"Удалить пресет `{_entry_title(entry)}` ({entry.preset.preset_id})?\n\n"
                f"Будут удалены его файлы и все {len(entry.preset.profiles)} профилей. "
            )
        else:
            names = "\n".join(f"• {_entry_title(entry)}" for entry in removable[:12])
            more = f"\n… и ещё {len(removable) - 12}" if len(removable) > 12 else ""
            text = f"Удалить {len(removable)} пресетов?\n\n{names}{more}\n\n"
        if skipped:
            text += f"Встроенные ({skipped}) не удаляются. "
        text += "Если удаляемый пресет выбран, выбор переключится на пресет по умолчанию. Runtime/firewall сейчас не меняются."
        question = QtWidgets.QMessageBox.question(page, "Удаление пресетов", text)
        if question != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        removed, errors = remove_presets([entry.preset.preset_id for entry in removable], root=root)
        lines = [f"Удалено пресетов: {len(removed)}"] + [f"  {item.preset_id}" for item in removed]
        if errors:
            lines += ["", "Не удалены:"] + [f"  {item}" for item in errors]
        details.setPlainText("\n".join(lines))
        refresh(selected_preset_id=removed[-1].selected_preset_id if removed else None)
        if errors:
            QtWidgets.QMessageBox.warning(page, "Удалены не все пресеты", "\n".join(errors[:8]))

    def import_preset_txt() -> None:
        filename, _selected_filter = QtWidgets.QFileDialog.getOpenFileName(
            page,
            "Импорт полного Zapret2 пресета",
            "",
            "Zapret TXT preset (*.txt);;Все файлы (*)",
        )
        if not filename:
            return
        try:
            analysis = analyze_txt_preset(Path(filename), root)
        except Exception as exc:
            QtWidgets.QMessageBox.critical(
                page,
                "TXT не распознан как пресет",
                str(exc),
            )
            return
        if not analysis.can_import:
            details.setPlainText(analysis.to_text())
            message = "\n".join(item.message for item in analysis.errors) or "Preset не прошёл import validation"
            QtWidgets.QMessageBox.critical(page, "Пресет не импортирован", message)
            return

        dependency_root: Path | None = None
        if analysis.missing_list_dependencies:
            root_hint = ""
            if analysis.dependency_root_hint is not None:
                root_hint = (
                    f"\n\nАвтопоиск package root: {analysis.dependency_root_hint}"
                    f"\nпричина: {analysis.dependency_root_reason or 'ancestor'}; "
                    f"coverage: {analysis.dependency_root_coverage or '0/0'}."
                )
            answer = QtWidgets.QMessageBox.question(
                page,
                "Внешние списки пресета",
                (
                    f"TXT ссылается на {len(analysis.missing_list_dependencies)} hostlist/ipset files, "
                    "которых не удалось разрешить автоматически."
                    f"{root_hint}\n\n"
                    "Да — выбрать другой корень исходного пакета (каталог, внутри которого находится lists).\n"
                    "Нет — импортировать пресет как неполный; его runtime-запуск будет заблокирован.\n"
                    "Отмена — не импортировать."
                ),
                QtWidgets.QMessageBox.StandardButton.Yes
                | QtWidgets.QMessageBox.StandardButton.No
                | QtWidgets.QMessageBox.StandardButton.Cancel,
                QtWidgets.QMessageBox.StandardButton.Yes,
            )
            if answer == QtWidgets.QMessageBox.StandardButton.Cancel:
                details.setPlainText(analysis.to_text())
                return
            if answer == QtWidgets.QMessageBox.StandardButton.Yes:
                directory = QtWidgets.QFileDialog.getExistingDirectory(
                    page,
                    "Корень пакета с hostlist/ipset",
                    str(analysis.dependency_root_hint or Path(filename).parent),
                )
                if not directory:
                    details.setPlainText(analysis.to_text())
                    return
                dependency_root = Path(directory)
                try:
                    analysis = analyze_txt_preset(Path(filename), root, dependency_root=dependency_root)
                except Exception as exc:
                    QtWidgets.QMessageBox.critical(page, "Зависимости пресета не прочитаны", str(exc))
                    return

        warning_text = ""
        if analysis.warnings:
            warning_text = (
                "\n\nПредупреждения: "
                + "; ".join(item.message for item in analysis.warnings[:3])
                + ("; …" if len(analysis.warnings) > 3 else "")
            )
        question = QtWidgets.QMessageBox.question(
            page,
            "Импорт TXT пресета",
            (
                f"Импортировать `{analysis.title}` как полный owner-managed preset?\n\n"
                f"Распознано профилей: {len(analysis.parsed_preset.profiles)}; "
                f"lua-desync actions: {analysis.parsed_preset.action_count}; "
                f"confidence: {analysis.confidence}.\n"
                "Windows-only/runtime-owned flags не попадут в Linux runtime; известные Lua/blob paths "
                "будут переписаны на vendored core. Найденные companion hostlist/ipset будут скопированы "
                "в project-owned assets; при оставшихся missing files runtime будет заблокирован до исправления. "
                "Runtime и nftables сейчас не запускаются."
                f"{warning_text}"
            ),
        )
        if question != QtWidgets.QMessageBox.StandardButton.Yes:
            details.setPlainText(analysis.to_text())
            return
        try:
            result = import_txt_preset(Path(filename), root, dependency_root=dependency_root)
            details.setPlainText(result.to_text())
            refresh(selected_preset_id=result.preset_id)
        except Exception as exc:
            QtWidgets.QMessageBox.critical(page, "Пресет не импортирован", str(exc))


    def add_profile() -> None:
        preset_id = _current_preset_id()
        if not preset_id or not state.get("managed"):
            return
        profile = edit_traffic_profile_dialog(page, root)
        if profile is None:
            return
        try:
            result = add_owner_preset_profile(preset_id, profile, root=root)
            details.setPlainText(result.to_text())
            refresh(selected_preset_id=preset_id, select_row=max(0, result.profile_count - 1))
        except Exception as exc:
            QtWidgets.QMessageBox.critical(page, "Профиль не добавлен", str(exc))

    def edit_profile() -> None:
        entry = state.get("entry")
        row = profile_table.currentRow()
        if entry is None or row < 0 or not state.get("managed"):
            return
        initial = editable_profile_from_runtime(entry.preset.profiles[row])
        profile = edit_traffic_profile_dialog(page, root, initial)
        if profile is None:
            return
        try:
            result = update_owner_preset_profile(entry.preset.preset_id, row, profile, root=root)
            details.setPlainText(result.to_text())
            refresh(selected_preset_id=entry.preset.preset_id, select_row=row)
        except Exception as exc:
            QtWidgets.QMessageBox.critical(page, "Профиль не изменён", str(exc))

    def remove_profile() -> None:
        entry = state.get("entry")
        row = profile_table.currentRow()
        if entry is None or row < 0 or not state.get("managed"):
            return
        profile = entry.preset.profiles[row]
        question = QtWidgets.QMessageBox.question(
            page,
            "Удаление профиля",
            f"Удалить профиль #{row + 1} `{profile.name}` из preset `{entry.preset.preset_id}`?",
        )
        if question != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        try:
            result = remove_owner_preset_profile(entry.preset.preset_id, row, root=root)
            details.setPlainText(result.to_text())
            refresh(selected_preset_id=entry.preset.preset_id, select_row=max(0, row - 1))
        except Exception as exc:
            QtWidgets.QMessageBox.critical(page, "Профиль не удалён", str(exc))

    def move_profile(delta: int) -> None:
        row = profile_table.currentRow()
        move_profile_to(row, row + delta)

    def move_profile_to(row: int, new_row: int) -> None:
        entry = state.get("entry")
        if entry is None or row < 0 or not state.get("managed"):
            return
        if not 0 <= new_row < len(entry.preset.profiles) or new_row == row:
            return
        try:
            result = move_owner_preset_profile(entry.preset.preset_id, row, new_row, root=root)
            details.setPlainText(result.to_text())
            refresh(selected_preset_id=entry.preset.preset_id, select_row=new_row)
        except Exception as exc:
            QtWidgets.QMessageBox.critical(page, "Порядок не изменён", str(exc))

    def _apply_search() -> None:
        query = search_edit.text().strip().lower()
        words = tuple(part for part in query.split() if part)
        for index in range(preset_list.count()):
            item = preset_list.item(index)
            haystack = item.text().lower()
            item.setHidden(bool(words) and not all(word in haystack for word in words))
        refresh_strat()

    def _current_strat_entry() -> Any | None:
        row = collection_table.currentRow()
        rows = state.get("strat_rows") or []
        if not 0 <= row < len(rows):
            return None
        return rows[row]

    def _strat_plan(entry: Any) -> Any:
        cache = state.setdefault("strat_plans", {})
        if entry.entry_id not in cache:
            cache[entry.entry_id] = analyze_strat_port(entry, root)
        return cache[entry.entry_id]

    def _existing_strat_ports() -> dict[str, str]:
        catalog = state.get("catalog") or load_preset_catalog(root)
        result: dict[str, str] = {}
        for item in catalog.entries:
            source = item.metadata.source_preset or {}
            entry_id = str(source.get("stratCollectionEntryId") or "")
            if entry_id:
                result[entry_id] = item.preset.preset_id
        return result

    def _update_apply_button() -> None:
        if state.get("busy"):
            select_button.setEnabled(False)
            return
        if tabs.currentIndex() == 0:
            select_button.setText("Применить пресет")
            select_button.setToolTip("Выбрать Zapret2 preset и применить его через hot-swap")
            select_button.setEnabled(bool(_current_preset_id()))
            return
        entry = _current_strat_entry()
        if entry is None:
            select_button.setText("Автопорт недоступен")
            select_button.setToolTip("Выберите стратегию strat_collection")
            select_button.setEnabled(False)
            return
        existing = _existing_strat_ports().get(entry.entry_id, "")
        if existing:
            select_button.setText("Применить порт")
            select_button.setToolTip(f"Применить уже созданный Zapret2 preset: {existing}")
            select_button.setEnabled(True)
            return
        plan = _strat_plan(entry)
        if plan.can_port:
            select_button.setText("Портировать + применить")
            select_button.setToolTip("Создать owner-managed Zapret2 preset по явным mappings и применить через hot-swap")
            select_button.setEnabled(True)
        else:
            select_button.setText("Автопорт недоступен")
            reason = "; ".join(plan.unsupported[:3]) or "неоднозначная legacy-стратегия"
            select_button.setToolTip("Безопасный автопорт заблокирован: " + reason)
            select_button.setEnabled(False)

    def _show_strat_details() -> None:
        entry = _current_strat_entry()
        if entry is None:
            _update_apply_button()
            return
        state["strat_selected_id"] = entry.entry_id
        base_root = root if root is not None else state["strat"].root.parents[2]
        plan = _strat_plan(entry)
        existing = _existing_strat_ports().get(entry.entry_id, "")
        extra = ["", plan.to_text()]
        if existing:
            extra.extend(["", f"existing Zapret2 port: {existing}"])
        collection_details.setPlainText(entry.to_text(base_root) + "\n" + "\n".join(extra))
        _update_apply_button()

    def refresh_strat() -> None:
        try:
            catalog = state.get("strat") or load_strat_collection(root)
            state["strat"] = catalog
            desired_id = str(state.get("strat_selected_id") or "")
            rows = list(catalog.search(search_edit.text()))
            state["strat_rows"] = rows
            collection_table.setRowCount(len(rows))
            selected_row = -1
            for row, entry in enumerate(rows):
                plan = _strat_plan(entry)
                existing = _existing_strat_ports().get(entry.entry_id, "")
                compatibility = "Zapret2 port готов" if existing else ("автопорт Zapret2" if plan.can_port else "legacy / read-only")
                values = (
                    entry.name,
                    entry.provider or "-",
                    entry.label or "-",
                    entry.ports or "-",
                    ", ".join(entry.desync_modes) or "-",
                    compatibility,
                )
                for column, value in enumerate(values):
                    item = QtWidgets.QTableWidgetItem(value)
                    if column == 0:
                        item.setData(_user_role(), entry.entry_id)
                    collection_table.setItem(row, column, item)
                if entry.entry_id == desired_id:
                    selected_row = row
            if rows:
                if selected_row < 0:
                    selected_row = 0
                collection_table.selectRow(selected_row)
                _show_strat_details()
            else:
                collection_details.setPlainText("Ничего не найдено")
                _update_apply_button()
        except Exception as exc:
            collection_details.setPlainText(f"strat_collection: ошибка\n{exc}")
            _update_apply_button()

    def apply_current_strat() -> None:
        entry = _current_strat_entry()
        if entry is None or state.get("busy"):
            return
        state["strat_selected_id"] = entry.entry_id
        existing = _existing_strat_ports().get(entry.entry_id, "")
        plan = _strat_plan(entry)
        if not existing and not plan.can_port:
            message = "\n".join(plan.unsupported[:8]) or "Нет безопасного однозначного mapping."
            QtWidgets.QMessageBox.warning(
                page,
                "Автопорт strat_collection недоступен",
                "Эта legacy-стратегия не будет угадываться или исполняться через winws.\n\n" + message,
            )
            collection_details.setPlainText(plan.to_text())
            _update_apply_button()
            return
        if not existing:
            answer = QtWidgets.QMessageBox.question(
                page,
                "Портировать strat_collection в Zapret2",
                (
                    f"Создать owner-managed Zapret2 preset из `{entry.name}` и сразу применить его?\n\n"
                    "Будут перенесены только опции с явным соответствием в vendored Zapret2; Windows capture flags удаляются. "
                    "BAT/winws не запускаются. Исходная запись strat_collection не изменяется."
                ),
            )
            if answer != QtWidgets.QMessageBox.StandardButton.Yes:
                return

        state["busy"] = True
        page.setCursor(QtCore.Qt.CursorShape.WaitCursor)
        _update_apply_button()
        try:
            port_text = ""
            preset_id = existing
            if not preset_id:
                mutation = port_strat_collection_entry(entry.entry_id, root)
                preset_id = mutation.preset_id
                port_text = mutation.to_text() + "\n\n"
            result = hot_swap_preset(preset_id, root=root, profile_id="default", reason="gui-strat-collection-port")
            collection_details.setPlainText(port_text + result.to_text())
            refresh(selected_preset_id=result.selected_preset_id)
            tabs.setCurrentIndex(1)
            if not result.success:
                QtWidgets.QMessageBox.warning(page, "Hot-swap завершён с ошибкой", result.message)
        except Exception as exc:
            collection_details.setPlainText(f"strat_collection port/hot-swap: ошибка\n{exc}")
            QtWidgets.QMessageBox.critical(page, "strat_collection не применён", str(exc))
        finally:
            state["busy"] = False
            page.unsetCursor()
            refresh_strat()
            _update_apply_button()

    def apply_current_selection() -> None:
        if tabs.currentIndex() == 1:
            apply_current_strat()
        else:
            apply_current_preset()

    preset_list.currentItemChanged.connect(lambda _current, _previous: _fill_profiles())
    preset_list.itemDoubleClicked.connect(double_click_apply)
    copy_preset_button.clicked.connect(lambda _checked=False: copy_preset())
    preset_list.itemSelectionChanged.connect(_update_remove_button)
    preset_list.customContextMenuRequested.connect(show_preset_menu)
    exclusions_button.clicked.connect(lambda _checked=False: edit_global_exclusions())
    overlap_list.currentRowChanged.connect(lambda _row: _show_fixes())
    for position, button in enumerate(fix_buttons):
        button.clicked.connect(lambda _checked=False, position=position: apply_fix(position))
    simulate_open_button.clicked.connect(lambda _checked=False: open_simulator())
    profile_table.itemSelectionChanged.connect(_show_profile_details)
    new_preset_button.clicked.connect(create_preset)
    import_preset_button.clicked.connect(import_preset_txt)
    remove_preset_button.clicked.connect(remove_preset)
    new_profile_button.clicked.connect(add_profile)
    edit_profile_button.clicked.connect(edit_profile)
    remove_profile_button.clicked.connect(remove_profile)
    move_up_button.clicked.connect(lambda _checked=False: move_profile(-1))
    move_down_button.clicked.connect(lambda _checked=False: move_profile(1))
    refresh_button.clicked.connect(lambda _checked=False: refresh(selected_preset_id=_current_preset_id()))
    select_button.clicked.connect(lambda _checked=False: apply_current_selection())
    catalog_button.clicked.connect(lambda _checked=False: details.setPlainText(preset_catalog_to_text(root)))
    collection_table.itemSelectionChanged.connect(_show_strat_details)
    tabs.currentChanged.connect(lambda _index: _update_apply_button())
    search_edit.textChanged.connect(lambda _text: _apply_search())
    search_clear.clicked.connect(search_edit.clear)
    find_shortcut = QtGui.QShortcut(QtGui.QKeySequence("Ctrl+F"), page)
    find_shortcut.activated.connect(lambda: (search_edit.setFocus(), search_edit.selectAll()))

    layout.addWidget(title)
    layout.addWidget(intro)
    layout.addLayout(search_row)
    layout.addLayout(buttons)
    layout.addWidget(tabs, 1)
    refresh()
    refresh_strat()

    # В маленьком окне страница прокручивается, а не сжимает таблицу профилей до нуля.
    page.setMinimumHeight(620)
    scroll = QtWidgets.QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setWidget(page)
    return scroll
