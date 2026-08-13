"""PyQt каталог и конструктор: пресет -> ordered traffic profiles."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..adapters.preset_editor import (
    add_owner_preset_profile,
    create_owner_preset,
    editable_profile_from_runtime,
    is_preset_editor_managed,
    move_owner_preset_profile,
    remove_owner_preset,
    remove_owner_preset_profile,
    update_owner_preset_profile,
)
from ..adapters.presets import (
    load_preset_catalog,
    preset_catalog_to_text,
    select_preset,
    traffic_profile_to_text,
)
from ..adapters.preset_txt_import import analyze_txt_preset, import_txt_preset
from ..qt_compat import require_pyqt
from .preset_constructor import edit_traffic_profile_dialog


_PROFILE_COLUMNS = ("#", "Профиль", "Фильтр", "Стратегия", "Range", "Direction")


def _preset_item_text(entry: Any, selected_preset_id: str) -> str:
    preset = entry.preset
    marker = " ✓" if preset.preset_id == selected_preset_id else ""
    managed = " · constructor" if bool((entry.metadata.source_preset or {}).get("editorManaged")) else ""
    return (
        f"{preset.title}{marker}\n"
        f"профилей: {len(preset.profiles)} · действий: {preset.action_count}{managed}\n"
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
        "Пресет — это полный набор параметров nfqws2. Профили проверяются сверху вниз: "
        "при первом совпадении filter выбирается один профиль. Конструктор меняет только файлы проекта; "
        "запуск остаётся за plan и owner confirmation."
    )
    intro.setWordWrap(True)

    status = QtWidgets.QLabel("")
    status.setObjectName("mutedText")

    buttons = QtWidgets.QHBoxLayout()
    new_preset_button = QtWidgets.QPushButton("+ Пресет")
    import_preset_button = QtWidgets.QPushButton("Импорт .txt")
    remove_preset_button = QtWidgets.QPushButton("Удалить пресет")
    new_profile_button = QtWidgets.QPushButton("+ Профиль")
    edit_profile_button = QtWidgets.QPushButton("Изменить")
    remove_profile_button = QtWidgets.QPushButton("Удалить профиль")
    move_up_button = QtWidgets.QPushButton("↑")
    move_down_button = QtWidgets.QPushButton("↓")
    refresh_button = QtWidgets.QPushButton("Обновить")
    select_button = QtWidgets.QPushButton("Выбрать пресет")
    catalog_button = QtWidgets.QPushButton("Сводка")
    for button in (
        new_preset_button,
        import_preset_button,
        remove_preset_button,
        new_profile_button,
        edit_profile_button,
        remove_profile_button,
        move_up_button,
        move_down_button,
    ):
        buttons.addWidget(button)
    buttons.addSpacing(12)
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
    preset_list.setMinimumWidth(320)
    preset_list.setAlternatingRowColors(True)

    right = QtWidgets.QWidget()
    right_layout = QtWidgets.QVBoxLayout(right)
    right_layout.setContentsMargins(0, 0, 0, 0)
    right_layout.setSpacing(8)

    priority = QtWidgets.QLabel(
        "Порядок профилей — приоритет. Строка выше выигрывает при пересечении фильтров. "
        "Reference/community пресеты доступны только для чтения; изменяются только presets с пометкой constructor."
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

    state: dict[str, Any] = {"catalog": None, "entry": None, "managed": False}

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
        remove_preset_button.setEnabled(managed)
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
                profile_table.setItem(row, column, item)

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

    def refresh(selected_preset_id: str | None = None, select_row: int = 0) -> None:
        preset_list.clear()
        profile_table.setRowCount(0)
        try:
            catalog = load_preset_catalog(root)
            state["catalog"] = catalog
            active = selected_preset_id or _current_preset_id() or catalog.selected_preset_id
            for entry in catalog.entries:
                item = QtWidgets.QListWidgetItem(_preset_item_text(entry, catalog.selected_preset_id))
                item.setData(_user_role(), entry.preset.preset_id)
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
                f"Выбрать preset `{preset_id}` для Default workspace?\n\n"
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

    def remove_preset() -> None:
        entry = state.get("entry")
        if entry is None or not state.get("managed"):
            return
        question = QtWidgets.QMessageBox.question(
            page,
            "Удаление пресета",
            (
                f"Удалить весь owner-managed preset `{entry.preset.title}` "
                f"({entry.preset.preset_id})?\n\n"
                f"Будут удалены preset metadata и все {len(entry.preset.profiles)} profiles. "
                "Если preset выбран, selection переключится на catalog default. "
                "Runtime/firewall сейчас не меняются."
            ),
        )
        if question != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        try:
            result = remove_owner_preset(entry.preset.preset_id, root=root)
            details.setPlainText(result.to_text())
            refresh(selected_preset_id=result.selected_preset_id)
        except Exception as exc:
            QtWidgets.QMessageBox.critical(page, "Пресет не удалён", str(exc))


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
        entry = state.get("entry")
        row = profile_table.currentRow()
        new_row = row + delta
        if entry is None or row < 0 or not state.get("managed"):
            return
        if not 0 <= new_row < len(entry.preset.profiles):
            return
        try:
            result = move_owner_preset_profile(entry.preset.preset_id, row, new_row, root=root)
            details.setPlainText(result.to_text())
            refresh(selected_preset_id=entry.preset.preset_id, select_row=new_row)
        except Exception as exc:
            QtWidgets.QMessageBox.critical(page, "Порядок не изменён", str(exc))

    preset_list.currentItemChanged.connect(lambda _current, _previous: _fill_profiles())
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
    select_button.clicked.connect(lambda _checked=False: choose_preset())
    catalog_button.clicked.connect(lambda _checked=False: details.setPlainText(preset_catalog_to_text(root)))

    layout.addWidget(title)
    layout.addWidget(intro)
    layout.addLayout(buttons)
    layout.addWidget(status)
    layout.addWidget(outer_splitter, 1)
    refresh()
    return page
