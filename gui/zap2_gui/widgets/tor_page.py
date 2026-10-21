"""Страница «Tor»: режим использования, мосты и pluggable transports, запуск с прогрессом загрузки."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from ..adapters.runtime_state import confirm_runtime_plan
from ..adapters.tor_backends import (
    TorSettings,
    ensure_tor_backend_store,
    load_tor_settings,
    save_tor_settings,
    tor_backend_plan_to_text,
    tor_backend_start_to_text,
    tor_backend_status_to_text,
    tor_backend_stop_to_text,
    tor_bootstrap_status,
)
from ..adapters.tor_bridges import detect_transport_programs, load_bridges, parse_bridges, save_bridges
from ..qt_compat import require_pyqt

MODE_APPS = (
    "Tor поднимает локальный SOCKS-прокси; Discord (кнопка на странице «Туннель») и любые "
    "программы с настройкой прокси ходят через сеть Tor. Больше анонимности — меньше скорость; голос Discord (UDP) "
    "через Tor не работает."
)
MODE_CHAIN = (
    "Туннель VLESS подключается к своему серверу через Tor: провайдер видит только Tor, а сервер VLESS "
    "видит выходной узел Tor вместо вашего адреса. Больше скрытности — меньше скорость; нужен рабочий профиль VLESS "
    "на странице «Туннель», Tor должен слушать порт (не unix-сокет), а план туннеля готовится после запуска Tor."
)
BRIDGES_HELP = (
    "Мосты нужны, если Tor заблокирован. Где взять: bridges.torproject.org (в браузере), бот @GetBridgesBot в Telegram "
    "или письмо на bridges@torproject.org. Вставьте строки как есть — по одной на строку, с «Bridge» или без. "
    "Программа сама мосты не запрашивает: обращение к сервису мостов (Moat) уже показывает наблюдателю, что вы ищете Tor."
)
LISTEN_WARNING = (
    "Порт на 127.0.0.1 доступен любой программе и любому пользователю этой машины: localhost — не приватность. "
    "Случайный порт сложнее найти сканированием, но это не защита. Unix-сокет лежит в каталоге с правами 0700 и доступен "
    "только вам, но им умеют пользоваться не все программы (Discord и режим «Tor перед VLESS» — нет)."
)
PLAN_ID = "runtime-default-tor-{backend}-start-plan"


def make_tor_page(root: Path | None = None) -> Any:
    QtCore, QtWidgets = require_pyqt()
    from PyQt6 import QtGui  # type: ignore[import-not-found]

    paths = ensure_tor_backend_store(root)
    settings = load_tor_settings(root)

    page = QtWidgets.QWidget()
    layout = QtWidgets.QVBoxLayout(page)
    layout.setContentsMargins(12, 12, 8, 12)
    layout.setSpacing(10)

    title = QtWidgets.QLabel("Tor")
    title.setObjectName("pageTitle")
    intro = QtWidgets.QLabel(
        "Tor пригодится, когда сайт заблокирован по IP и обход DPI не помогает, или когда важно скрыть, куда вы ходите. "
        "Используется системный C Tor или Arti; программа пишет только свой конфиг в рабочий каталог и не трогает firewall."
    )
    intro.setWordWrap(True)

    # 1. Режим
    mode_box = QtWidgets.QGroupBox("1. Как использовать Tor")
    mode_layout = QtWidgets.QVBoxLayout(mode_box)
    mode_apps = QtWidgets.QRadioButton("Приложения через Tor")
    mode_chain = QtWidgets.QRadioButton("Tor перед VLESS")
    mode_apps_hint = QtWidgets.QLabel(MODE_APPS)
    mode_chain_hint = QtWidgets.QLabel(MODE_CHAIN)
    for hint in (mode_apps_hint, mode_chain_hint):
        hint.setWordWrap(True)
        hint.setObjectName("mutedText")
    (mode_chain if settings.vless_via_tor else mode_apps).setChecked(True)
    mode_layout.addWidget(mode_apps)
    mode_layout.addWidget(mode_apps_hint)
    mode_layout.addWidget(mode_chain)
    mode_layout.addWidget(mode_chain_hint)

    # 2. Мосты
    bridges_box = QtWidgets.QGroupBox("2. Мосты")
    bridges_layout = QtWidgets.QVBoxLayout(bridges_box)
    use_bridges = QtWidgets.QCheckBox("Подключаться через мосты")
    use_bridges.setChecked(settings.use_bridges)
    bridges_help = QtWidgets.QLabel(BRIDGES_HELP)
    bridges_help.setWordWrap(True)
    bridges_help.setObjectName("mutedText")
    bridges_edit = QtWidgets.QPlainTextEdit("\n".join(item.line for item in load_bridges(paths.tor_root)))
    bridges_edit.setPlaceholderText("obfs4 192.0.2.10:443 0123456789ABCDEF0123456789ABCDEF01234567 cert=… iat-mode=0")
    bridges_edit.setMinimumHeight(90)
    bridges_edit.setMaximumHeight(150)
    bridges_edit.setObjectName("torBridges")
    bridges_buttons = QtWidgets.QHBoxLayout()
    save_bridges_button = QtWidgets.QPushButton("Проверить и сохранить")
    refresh_pt_button = QtWidgets.QPushButton("Найти транспорты")
    bridges_buttons.addWidget(save_bridges_button)
    bridges_buttons.addWidget(refresh_pt_button)
    bridges_buttons.addStretch(1)
    bridges_result = QtWidgets.QLabel("")
    bridges_result.setWordWrap(True)
    pt_status = QtWidgets.QLabel("")
    pt_status.setWordWrap(True)
    pt_status.setObjectName("mutedText")
    bridges_layout.addWidget(use_bridges)
    bridges_layout.addWidget(bridges_help)
    bridges_layout.addWidget(bridges_edit)
    bridges_layout.addLayout(bridges_buttons)
    bridges_layout.addWidget(bridges_result)
    bridges_layout.addWidget(pt_status)

    # 3. Запуск
    run_box = QtWidgets.QGroupBox("3. Запуск")
    run_layout = QtWidgets.QGridLayout(run_box)
    backend_combo = QtWidgets.QComboBox()
    backend_combo.addItem("C Tor (системный пакет tor)", "c-tor")
    backend_combo.addItem("Arti (Tor на Rust)", "arti")
    backend_combo.setCurrentIndex(max(0, backend_combo.findData(settings.backend)))
    binary_edit = QtWidgets.QLineEdit(settings.binary)
    binary_edit.setPlaceholderText("пусто = tor или arti из PATH")
    binary_edit.setObjectName("torBackendBinary")
    listen_combo = QtWidgets.QComboBox()
    listen_combo.addItem("Случайный порт (рекомендуется)", "random")
    listen_combo.addItem("Фиксированный порт", "port")
    listen_combo.addItem("Unix-сокет (только C Tor)", "unix")
    listen_combo.setCurrentIndex(max(0, listen_combo.findData(settings.listen)))
    port_spin = QtWidgets.QSpinBox()
    port_spin.setRange(1024, 65535)
    port_spin.setValue(settings.port)
    listen_warning = QtWidgets.QLabel(LISTEN_WARNING)
    listen_warning.setWordWrap(True)
    listen_warning.setObjectName("mutedText")
    start_button = QtWidgets.QPushButton("Запустить Tor")
    start_button.setObjectName("primaryRunButton")
    stop_button = QtWidgets.QPushButton("Остановить")
    status_button = QtWidgets.QPushButton("Статус")
    copy_button = QtWidgets.QPushButton("Скопировать адрес прокси")
    progress = QtWidgets.QProgressBar()
    progress.setRange(0, 100)
    progress.setValue(0)
    progress.setFormat("Tor не запущен")
    run_layout.addWidget(QtWidgets.QLabel("Программа"), 0, 0)
    run_layout.addWidget(backend_combo, 0, 1)
    run_layout.addWidget(binary_edit, 0, 2, 1, 2)
    run_layout.addWidget(QtWidgets.QLabel("Где слушать"), 1, 0)
    run_layout.addWidget(listen_combo, 1, 1)
    run_layout.addWidget(port_spin, 1, 2)
    run_layout.addWidget(listen_warning, 2, 0, 1, 4)
    buttons = QtWidgets.QHBoxLayout()
    for button in (start_button, stop_button, status_button, copy_button):
        buttons.addWidget(button)
    buttons.addStretch(1)
    run_layout.addLayout(buttons, 3, 0, 1, 4)
    run_layout.addWidget(progress, 4, 0, 1, 4)
    run_layout.setColumnStretch(3, 1)

    output = QtWidgets.QPlainTextEdit()
    output.setReadOnly(True)
    output.setMinimumHeight(140)
    output.setObjectName("torOutput")

    layout.addWidget(title)
    layout.addWidget(intro)
    layout.addWidget(mode_box)
    layout.addWidget(bridges_box)
    layout.addWidget(run_box)
    layout.addWidget(output, 1)

    timer = QtCore.QTimer(page)
    timer.setInterval(1000)
    state: dict[str, Any] = {"socks": ""}

    def current_settings() -> TorSettings:
        return TorSettings(
            backend=str(backend_combo.currentData()),
            binary=binary_edit.text().strip(),
            listen=str(listen_combo.currentData()),
            port=int(port_spin.value()),
            use_bridges=use_bridges.isChecked(),
            vless_via_tor=mode_chain.isChecked(),
        )

    def remember() -> None:
        try:
            save_tor_settings(current_settings(), root)
        except OSError as exc:  # pragma: no cover - GUI diagnostic path
            output.setPlainText(f"Настройки Tor не сохранены: {exc}")

    def sync_controls() -> None:
        is_arti = backend_combo.currentData() == "arti"
        unix_index = listen_combo.findData("unix")
        item = listen_combo.model().item(unix_index)
        if item is not None:
            item.setEnabled(not is_arti)
        if is_arti and listen_combo.currentData() == "unix":
            listen_combo.setCurrentIndex(listen_combo.findData("random"))
        port_spin.setEnabled(listen_combo.currentData() == "port")
        if mode_chain.isChecked() and listen_combo.currentData() == "unix":
            listen_combo.setCurrentIndex(listen_combo.findData("random"))

    def show_transports() -> None:
        programs = detect_transport_programs()
        parsed = parse_bridges(bridges_edit.toPlainText())
        missing = programs.missing_for(parsed.transports)
        text = "Транспорты на этой машине:\n" + programs.to_text()
        if missing:
            text += "\n\nДля вставленных мостов не хватает: " + ", ".join(missing)
        pt_status.setText(text)

    def save_bridge_list() -> None:
        parsed = parse_bridges(bridges_edit.toPlainText())
        if parsed.errors:
            bridges_result.setText("Не сохранено, исправьте строки:\n" + "\n".join(parsed.errors[:8]))
            return
        save_bridges(paths.tor_root, parsed.bridges)
        bridges_edit.setPlainText("\n".join(item.line for item in parsed.bridges))
        kinds = ", ".join(parsed.transports) or "обычные"
        note = f" Повторы убраны: {parsed.duplicates}." if parsed.duplicates else ""
        bridges_result.setText(f"Сохранено мостов: {len(parsed.bridges)} ({kinds}).{note}" if parsed.bridges else "Список мостов очищен.")
        if parsed.bridges and not use_bridges.isChecked():
            use_bridges.setChecked(True)
        remember()
        show_transports()

    def poll() -> None:
        status = tor_bootstrap_status(root=root)
        state["socks"] = status.socks
        if status.percent is not None:
            progress.setValue(status.percent)
        if status.state == "ready":
            progress.setFormat(f"Готов · {status.socks}")
            timer.stop()
        elif status.state == "starting":
            progress.setFormat(f"Загрузка %p% · {status.summary}")
        elif status.state == "failed":
            progress.setFormat("Ошибка: " + status.summary[:120])
            timer.stop()
        else:
            progress.setValue(0)
            progress.setFormat(status.summary)
            timer.stop()
        copy_button.setEnabled(status.state in {"ready", "starting"} and not status.socks.startswith("unix:"))

    def run(label: str, action: Callable[[], str]) -> None:
        try:
            output.setPlainText(action())
        except Exception as exc:
            output.setPlainText(f"{label}: ошибка\n{exc}")

    def start() -> str:
        chosen = current_settings()
        if chosen.use_bridges and not load_bridges(paths.tor_root):
            save_bridge_list()
        save_tor_settings(chosen, root)
        plan_text = tor_backend_plan_to_text(
            root=root,
            backend=chosen.backend,
            binary=chosen.binary or None,
            socks_port=chosen.port,
            listen=chosen.listen,
            use_bridges=chosen.use_bridges,
        )
        plan_id = PLAN_ID.format(backend=chosen.backend)
        confirm_runtime_plan(root=root, plan_id=plan_id)
        started = tor_backend_start_to_text(root=root, backend=chosen.backend, confirm_plan_id=plan_id)
        progress.setValue(0)
        progress.setFormat("Запуск…")
        timer.start()
        hint = ""
        if chosen.vless_via_tor:
            hint = "\n\nРежим «Tor перед VLESS»: когда Tor загрузится, на странице «Туннель» подготовьте план и запустите туннель заново."
        return started + hint + "\n\n" + plan_text

    def stop() -> str:
        timer.stop()
        text = tor_backend_stop_to_text(root=root)
        poll()
        return text

    def copy_address() -> None:
        address = state.get("socks") or ""
        if address and not address.startswith("unix:"):
            QtGui.QGuiApplication.clipboard().setText(address)
            output.setPlainText(f"Скопировано: {address}\nВ программе укажите SOCKS5-прокси с DNS через прокси (socks5h).")

    backend_combo.currentIndexChanged.connect(lambda _index: (sync_controls(), remember()))
    listen_combo.currentIndexChanged.connect(lambda _index: (sync_controls(), remember()))
    port_spin.valueChanged.connect(lambda _value: remember())
    binary_edit.editingFinished.connect(remember)
    use_bridges.toggled.connect(lambda _checked: remember())
    mode_apps.toggled.connect(lambda _checked: (sync_controls(), remember()))
    save_bridges_button.clicked.connect(lambda _checked=False: save_bridge_list())
    refresh_pt_button.clicked.connect(lambda _checked=False: show_transports())
    start_button.clicked.connect(lambda _checked=False: run("Запуск Tor", start))
    stop_button.clicked.connect(lambda _checked=False: run("Остановка Tor", stop))
    status_button.clicked.connect(lambda _checked=False: run("Статус Tor", lambda: (poll(), tor_backend_status_to_text(root=root))[1]))
    copy_button.clicked.connect(lambda _checked=False: copy_address())
    timer.timeout.connect(poll)

    sync_controls()
    show_transports()
    poll()
    if tor_bootstrap_status(root=root).state == "starting":
        timer.start()

    scroll = QtWidgets.QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setWidget(page)
    return scroll


__all__ = ["make_tor_page"]
