"""Страница «DNS»: каталог провайдеров, проверка, смена через NetworkManager и откат."""

from __future__ import annotations

import json
from pathlib import Path
import socket
from typing import Any, Callable, Optional
from urllib.parse import urlsplit

from ..adapters import dns_nm
from ..adapters.dns_probe import check_provider, detect_interception
from ..adapters.dnscrypt_config import LOCAL_DNSCRYPT, dnscrypt_available, dnscrypt_config, dnscrypt_steps
from ..models.dns_catalog import DnsCatalog, DnsProvider, custom_provider, load_dns_catalog, provider_from_dict
from ..qt_compat import require_pyqt

STATUS_BADGES = {"ok": "", "blocked": "⛔ часто блокируется", "at_risk": "⚠ под угрозой", "high_risk": "⚠ повышенный риск"}
FLAG_LABELS = {"dnssec": "DNSSEC", "adblock": "без рекламы", "family": "семейный фильтр", "encrypted_only": "только DoH/DoT"}


def _nm(argv: Any) -> dns_nm.Result:
    return dns_nm.run_nmcli(argv)  # поиск в модуле при вызове: тесты подменяют nmcli


def _runtime_root(root: Path | None) -> Path:
    from ..adapters.runtime_state import ensure_runtime_store

    return ensure_runtime_store(root).root


def custom_servers_path(root: Path | None) -> Path:
    return dns_nm.dns_state_dir(_runtime_root(root)) / "custom.json"


def load_custom_servers(root: Path | None) -> tuple[DnsProvider, ...]:
    try:
        raw = json.loads(custom_servers_path(root).read_text(encoding="utf-8"))
        return tuple(provider_from_dict(item, {"custom"}) for item in raw.get("providers", []))
    except (OSError, ValueError, KeyError):
        return ()


def save_custom_server(root: Path | None, provider: DnsProvider) -> None:
    items = [p for p in load_custom_servers(root) if p.provider_id != provider.provider_id] + [provider]
    path = custom_servers_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"providers": [p.to_dict() for p in items]}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def resolve_doh_host(url: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    host = urlsplit(url).hostname or ""
    v4, v6 = [], []
    for family, _t, _p, _c, sockaddr in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM):
        (v4 if family == socket.AF_INET else v6).append(sockaddr[0])
    return tuple(dict.fromkeys(v4))[:2], tuple(dict.fromkeys(v6))[:2]


def provider_details(provider: DnsProvider, catalog: DnsCatalog) -> str:
    group = next((g for g in catalog.groups if g.group_id == provider.group), None)
    lines = [provider.name]
    if group:
        lines.append(f"{group.title}: {group.tradeoff}")
    if STATUS_BADGES.get(provider.status):
        lines.append(STATUS_BADGES[provider.status])
    if provider.note:
        lines.append(provider.note)
    lines.append("IPv4: " + (", ".join(provider.ipv4) or "—"))
    lines.append("IPv6: " + (", ".join(provider.ipv6) or "—"))
    lines.append("DoH: " + (provider.doh or "—"))
    lines.append("DoT: " + (provider.dot or "—"))
    if provider.flags:
        lines.append("Особенности: " + ", ".join(FLAG_LABELS.get(f, f) for f in provider.flags))
    return "\n".join(lines)


def make_dns_page(root: Path | None = None, navigate: Optional[Callable[[str], None]] = None) -> Any:
    QtCore, QtWidgets = require_pyqt()
    page = QtWidgets.QWidget()
    layout = QtWidgets.QVBoxLayout(page)
    layout.setContentsMargins(14, 14, 14, 14)
    layout.setSpacing(8)

    title = QtWidgets.QLabel("DNS")
    title.setObjectName("pageTitle")
    intro = QtWidgets.QLabel(
        "DNS превращает имя сайта в адрес. Провайдер может подменять или перехватывать ответы — тогда сайт «не существует» "
        "или открывается заглушка. Здесь можно проверить это, сменить DNS и вернуть как было."
    )
    intro.setWordWrap(True)
    layout.addWidget(title)
    layout.addWidget(intro)

    status_row = QtWidgets.QHBoxLayout()
    device_combo = QtWidgets.QComboBox()
    device_combo.setObjectName("dnsDeviceCombo")
    status_label = QtWidgets.QLabel()
    status_label.setObjectName("dnsCurrentStatus")
    status_label.setWordWrap(True)
    refresh_button = QtWidgets.QPushButton("Обновить")
    intercept_button = QtWidgets.QPushButton("Проверить перехват DNS")
    intercept_button.setObjectName("dnsInterceptButton")
    status_row.addWidget(QtWidgets.QLabel("Подключение:"))
    status_row.addWidget(device_combo)
    status_row.addWidget(refresh_button)
    status_row.addWidget(intercept_button)
    status_row.addStretch(1)
    layout.addLayout(status_row)
    layout.addWidget(status_label)

    body = QtWidgets.QHBoxLayout()
    tree = QtWidgets.QTreeWidget()
    tree.setObjectName("dnsProviderTree")
    tree.setHeaderLabels(["Сервер", "Коротко"])
    tree.setColumnWidth(0, 230)
    tree.setMinimumWidth(420)
    details = QtWidgets.QPlainTextEdit()
    details.setObjectName("dnsProviderDetails")
    details.setReadOnly(True)
    details.setPlaceholderText("Выберите группу или сервер: здесь будет, чем он лучше и чем хуже других")
    body.addWidget(tree, 3)
    body.addWidget(details, 2)
    layout.addLayout(body, 1)

    check_row = QtWidgets.QHBoxLayout()
    check_button = QtWidgets.QPushButton("Проверить")
    check_group_button = QtWidgets.QPushButton("Проверить группу")
    add_button = QtWidgets.QPushButton("Свой DoH…")
    encrypted_button = QtWidgets.QPushButton("Шифрованный…")
    encrypted_button.setObjectName("dnsEncryptedButton")
    check_button.setToolTip("Обычный DNS, DoT и DoH выбранного сервера: отвечает ли и за сколько; не подменяет ли ответы")
    add_button.setToolTip("Добавить свой сервер: достаточно адреса DoH, IP программа найдёт сама")
    encrypted_button.setToolTip("DoH через системный dnscrypt-proxy: готовый конфиг и точные команды")
    for widget in (check_button, check_group_button, add_button, encrypted_button):
        check_row.addWidget(widget)
    check_row.addStretch(1)
    layout.addLayout(check_row)

    apply_row = QtWidgets.QHBoxLayout()
    temporary = QtWidgets.QRadioButton("временно")
    temporary.setToolTip("nmcli device modify: профиль сети не меняется; после переподключения вернётся прежний DNS")
    temporary.setChecked(True)
    persistent = QtWidgets.QRadioButton("постоянно")
    persistent.setToolTip("nmcli connection modify: прежние значения сохраняются и возвращаются кнопкой «Вернуть»")
    use_ipv6 = QtWidgets.QCheckBox("и IPv6")
    use_ipv6.setChecked(True)
    apply_button = QtWidgets.QPushButton("Применить")
    apply_button.setObjectName("dnsApplyButton")
    revert_button = QtWidgets.QPushButton("Вернуть")
    revert_button.setObjectName("dnsRevertButton")
    revert_button.setToolTip("Вернуть DNS, который был до изменения программой")
    verdict_button = QtWidgets.QPushButton("Проверить сеть →")
    verdict_button.setObjectName("dnsVerdictButton")
    verdict_button.setVisible(navigate is not None)
    for widget in (apply_button, temporary, persistent, use_ipv6, revert_button):
        apply_row.addWidget(widget)
    apply_row.addStretch(1)
    apply_row.addWidget(verdict_button)
    layout.addLayout(apply_row)

    output = QtWidgets.QPlainTextEdit()
    output.setObjectName("dnsOutput")
    output.setReadOnly(True)
    output.setMaximumHeight(150)
    layout.addWidget(output)

    holder: dict[str, Any] = {"catalog": None}

    def catalog() -> DnsCatalog:
        if holder["catalog"] is None:
            holder["catalog"] = load_dns_catalog(custom=(*load_custom_servers(root), LOCAL_DNSCRYPT))
        return holder["catalog"]

    def fill_tree() -> None:
        tree.clear()
        cat = catalog()
        for group in cat.groups:
            members = cat.in_group(group.group_id)
            if not members:
                continue
            node = QtWidgets.QTreeWidgetItem([group.title, group.tradeoff])
            node.setToolTip(1, group.tradeoff)
            node.setFlags(QtCore.Qt.ItemFlag.ItemIsEnabled | QtCore.Qt.ItemFlag.ItemIsSelectable)
            font = node.font(0)
            font.setBold(True)
            node.setFont(0, font)
            tree.addTopLevelItem(node)
            for provider in members:
                summary = " · ".join(x for x in (STATUS_BADGES.get(provider.status, ""),
                                                 "только DoH/DoT" if not provider.plain_dns_works else "",
                                                 ", ".join(provider.ipv4[:2])) if x)
                item = QtWidgets.QTreeWidgetItem([provider.name, summary])
                item.setData(0, QtCore.Qt.ItemDataRole.UserRole, provider.provider_id)
                item.setToolTip(0, provider.note or group.tradeoff)
                node.addChild(item)
            node.setExpanded(True)

    def selected() -> DnsProvider | None:
        item = tree.currentItem()
        pid = item.data(0, QtCore.Qt.ItemDataRole.UserRole) if item is not None else None
        return catalog().by_id().get(pid) if pid else None

    def refresh_status() -> None:
        device_combo.clear()
        try:
            devices = dns_nm.real_connected_devices(_nm)
        except RuntimeError as exc:
            status_label.setText(f"NetworkManager недоступен: {exc}")
            return
        for device in devices:
            device_combo.addItem(f"{device.device} — {device.connection}", device.device)
        state = dns_nm.load_dns_state(_runtime_root(root))
        lines = [dns_nm.resolver_summary()]
        if devices:
            current = dns_nm.current_dns(str(device_combo.currentData()), _nm)
            lines.append("Сейчас DNS: " + (", ".join(current) or "от провайдера (DHCP)"))
        if state:
            lines.append(f"Изменён программой: {state.get('provider')} на {state.get('device')} "
                         f"({'постоянно' if state.get('mode') == 'persistent' else 'до переподключения'})")
        status_label.setText(" · ".join(lines))
        revert_button.setEnabled(bool(state))

    def run_in_background(label: str, job: Callable[[], str]) -> None:
        if holder.get("worker") is not None:
            return

        class _Worker(QtCore.QThread):  # type: ignore[misc, valid-type]
            done = QtCore.pyqtSignal(str)

            def run(self) -> None:  # pragma: no cover - фоновый поток
                try:
                    text = job()
                except Exception as exc:  # noqa: BLE001
                    text = f"{label}: ошибка — {exc}"
                self.done.emit(text)

        def finished(text: str) -> None:
            holder.pop("worker", None)
            output.setPlainText(text)
            refresh_status()

        output.setPlainText(f"{label}…")
        worker = _Worker()
        worker.done.connect(finished)
        holder["worker"] = worker
        worker.start()

    def check_selected() -> None:
        provider = selected()
        if provider is not None:
            run_in_background("Проверка", lambda: check_provider(provider).to_text())

    def check_group() -> None:
        provider = selected()
        item = tree.currentItem()
        group_id = provider.group if provider else None
        if group_id is None and item is not None:
            title = item.text(0)
            group_id = next((g.group_id for g in catalog().groups if g.title == title), None)
        if group_id:
            members = catalog().in_group(group_id)
            run_in_background("Проверка группы", lambda: "\n".join(check_provider(p).to_text() for p in members))

    def apply_selected() -> None:
        provider = selected()
        device = device_combo.currentData()
        if provider is None or not device:
            output.setPlainText("Выберите сервер и подключение")
            return
        mode = persistent.isChecked()
        run_in_background("Смена DNS", lambda: dns_nm.apply_dns(_runtime_root(root), str(device), provider,
                                                                persistent=mode, use_ipv6=use_ipv6.isChecked(), runner=_nm))

    def revert() -> None:
        run_in_background("Откат DNS", lambda: dns_nm.revert_dns(_runtime_root(root), _nm))

    def add_custom() -> None:
        url, ok = QtWidgets.QInputDialog.getText(page, "Свой DNS", "Адрес DoH (https://…/dns-query):")
        if not ok or not url.strip():
            return

        def job() -> str:
            v4, v6 = resolve_doh_host(url.strip())
            provider = custom_provider("", url.strip(), v4, v6)
            save_custom_server(root, provider)
            holder["catalog"] = None
            return f"Добавлен {provider.name}: {', '.join(provider.ipv4 + provider.ipv6)}"

        run_in_background("Свой DNS", job)
        QtCore.QTimer.singleShot(1500, fill_tree)

    def show_encrypted() -> None:
        provider = selected()
        if provider is None or not provider.doh:
            output.setPlainText("Выберите сервер с DoH: шифрованный режим строится на нём")
            return
        config_dir = dns_nm.dns_state_dir(_runtime_root(root))
        config_dir.mkdir(parents=True, exist_ok=True)
        path = config_dir / "dnscrypt-proxy.toml"
        path.write_text(dnscrypt_config(provider), encoding="utf-8")
        lines = ["Шифрованный DNS (DoH) через системный dnscrypt-proxy.",
                 "dnscrypt-proxy " + ("найден" if dnscrypt_available() else "не установлен: sudo pacman -S dnscrypt-proxy"),
                 f"Конфиг для {provider.name}: {path}", "", "Шаги (выполните сами, программа root не использует):"]
        lines += [f"  {i}. {step}" for i, step in enumerate(dnscrypt_steps(str(path)), 1)]
        output.setPlainText("\n".join(lines))

    tree.currentItemChanged.connect(lambda current, _prev: details.setPlainText(
        provider_details(catalog().by_id()[current.data(0, QtCore.Qt.ItemDataRole.UserRole)], catalog())
        if current is not None and current.data(0, QtCore.Qt.ItemDataRole.UserRole) else
        (current.text(1) if current is not None else "")))
    refresh_button.clicked.connect(lambda _c=False: refresh_status())
    device_combo.activated.connect(lambda _i: refresh_status())
    intercept_button.clicked.connect(lambda _c=False: run_in_background("Проверка перехвата", detect_interception))
    check_button.clicked.connect(lambda _c=False: check_selected())
    check_group_button.clicked.connect(lambda _c=False: check_group())
    apply_button.clicked.connect(lambda _c=False: apply_selected())
    revert_button.clicked.connect(lambda _c=False: revert())
    add_button.clicked.connect(lambda _c=False: add_custom())
    encrypted_button.clicked.connect(lambda _c=False: show_encrypted())
    if navigate is not None:
        verdict_button.clicked.connect(lambda _c=False: navigate("diagnostics"))

    fill_tree()
    page.refresh_runtime_state = refresh_status
    return page


__all__ = ["make_dns_page", "load_custom_servers", "save_custom_server", "provider_details", "resolve_doh_host"]
