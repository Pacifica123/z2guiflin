"""Диалоги конструктора owner-managed пресетов."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..adapters.blockcheck_gui import (
    BLOCKCHECK_DEAD_TARGET_GUARD_AUTO_STOP,
    BLOCKCHECK_SCAN_STOP_AFTER_FIRST_AVAILABLE,
    BlockcheckOptions,
    BlockcheckPortPrecheckMonitor,
    BlockcheckPreparationError,
    parse_blockcheck_available_strategies,
    parse_blockcheck_run_stats,
    prepare_blockcheck_execution,
    write_blockcheck_last_log,
)
from ..adapters.preset_editor import (
    EditableTrafficProfile,
    PRESET_PROTOCOL_ANY,
    PRESET_PROTOCOL_TCP,
    PRESET_PROTOCOL_UDP,
    PRESET_TARGET_DOMAINS,
    PRESET_TARGET_HOSTLIST,
    PRESET_TARGET_IPS,
    PRESET_TARGET_IPSET,
    PRESET_TARGET_NONE,
    ProfileStrategyTemplate,
    list_profile_strategy_templates,
    parse_manual_strategy_text,
    split_blockcheck_profile_args,
    strategy_args_to_text,
)
from ..models.service_targets import SERVICE_TARGET_CUSTOM, normalize_service_targets
from ..qt_compat import require_pyqt


def _accepted(QtWidgets: Any, result: int) -> bool:
    try:
        return result == int(QtWidgets.QDialog.DialogCode.Accepted)
    except Exception:  # pragma: no cover - compatibility
        return bool(result)


def _user_role(QtCore: Any) -> Any:
    try:
        return QtCore.Qt.ItemDataRole.UserRole
    except Exception:  # pragma: no cover
        return QtCore.Qt.UserRole


def _message_error(QtWidgets: Any, parent: Any, title: str, text: str) -> None:
    QtWidgets.QMessageBox.critical(parent, title, text)


def _blockcheck_modes(profile: EditableTrafficProfile) -> tuple[bool, bool, bool, bool]:
    l7 = {item.strip().lower() for item in profile.l7.split(",") if item.strip()}
    is_quic = profile.protocol == PRESET_PROTOCOL_UDP or "quic" in l7
    enable_http = profile.protocol == PRESET_PROTOCOL_TCP and "http" in l7 and "80" in profile.ports
    enable_tls = not is_quic
    return enable_http, enable_tls, enable_tls, is_quic


def run_profile_blockcheck_dialog(
    parent: Any,
    root: Path | None,
    profile: EditableTrafficProfile,
) -> tuple[tuple[str, ...], tuple[str, ...]] | None:
    """Прогнать compact Blockcheck и вернуть filters + strategy выбранного AVAILABLE."""

    QtCore, QtWidgets = require_pyqt()
    if profile.target_kind != PRESET_TARGET_DOMAINS:
        _message_error(
            QtWidgets,
            parent,
            "Blockcheck для профиля",
            "Прямой Blockcheck работает только с domain/URI targets. Для Discord Voice с IP/UDP range нужен отдельный voice probe, а не HTTP/TLS Blockcheck.",
        )
        return None
    l7 = {item.strip().lower() for item in profile.l7.split(",") if item.strip()}
    if profile.protocol == PRESET_PROTOCOL_UDP and "quic" not in l7:
        _message_error(
            QtWidgets,
            parent,
            "Blockcheck для профиля",
            "Стандартный Blockcheck проверяет domain QUIC/HTTP3, но не Discord Voice/STUN UDP. "
            "Для voice-профиля оставьте известную или ручную стратегию; отдельный voice probe нужен как самостоятельная диагностика.",
        )
        return None
    try:
        targets = normalize_service_targets(profile.target_value.replace(",", " "))
    except Exception as exc:
        _message_error(QtWidgets, parent, "Blockcheck для профиля", str(exc))
        return None

    dialog = QtWidgets.QDialog(parent)
    dialog.setWindowTitle(f"Blockcheck → профиль: {profile.name}")
    dialog.resize(920, 680)
    layout = QtWidgets.QVBoxLayout(dialog)

    info = QtWidgets.QLabel(
        "Проверка идёт по targets последовательно и останавливается после первого AVAILABLE. "
        "Найденная команда не создаёт отдельный preset: после выбора её action/range часть будет вставлена прямо в редактируемый профиль."
    )
    info.setWordWrap(True)
    layout.addWidget(info)

    status = QtWidgets.QLabel(f"Targets: {', '.join(targets)}")
    status.setObjectName("mutedText")
    layout.addWidget(status)

    output = QtWidgets.QPlainTextEdit()
    output.setReadOnly(True)
    output.setLineWrapMode(QtWidgets.QPlainTextEdit.LineWrapMode.NoWrap)
    layout.addWidget(output, 1)

    candidates = QtWidgets.QListWidget()
    candidates.setMinimumHeight(130)
    layout.addWidget(QtWidgets.QLabel("AVAILABLE candidates"))
    layout.addWidget(candidates)

    preview = QtWidgets.QPlainTextEdit()
    preview.setReadOnly(True)
    preview.setMaximumHeight(150)
    layout.addWidget(preview)

    buttons = QtWidgets.QHBoxLayout()
    start_button = QtWidgets.QPushButton("Запустить")
    stop_button = QtWidgets.QPushButton("Остановить")
    apply_button = QtWidgets.QPushButton("Вставить в профиль")
    close_button = QtWidgets.QPushButton("Закрыть")
    stop_button.setEnabled(False)
    apply_button.setEnabled(False)
    buttons.addWidget(start_button)
    buttons.addWidget(stop_button)
    buttons.addStretch(1)
    buttons.addWidget(apply_button)
    buttons.addWidget(close_button)
    layout.addLayout(buttons)

    state: dict[str, Any] = {
        "targets": list(targets),
        "target_index": 0,
        "process": None,
        "prepared": None,
        "stdout": [],
        "stderr": [],
        "monitor": None,
        "owner_stop": False,
        "auto_reason": "",
        "available": [],
        "result": None,
    }

    def append(text: str) -> None:
        if not text:
            return
        output.appendPlainText(text.rstrip("\n"))
        output.verticalScrollBar().setValue(output.verticalScrollBar().maximum())

    def set_running(value: bool) -> None:
        start_button.setEnabled(not value and not state["available"])
        stop_button.setEnabled(value)
        close_button.setEnabled(not value)
        apply_button.setEnabled(not value and candidates.currentRow() >= 0)

    def selected_candidate() -> Any | None:
        row = candidates.currentRow()
        available = state.get("available") or []
        return available[row] if 0 <= row < len(available) else None

    def show_candidate() -> None:
        item = selected_candidate()
        if item is None:
            preview.clear()
            apply_button.setEnabled(False)
            return
        filters, strategy = split_blockcheck_profile_args(item.runtime_args)
        preview.setPlainText(
            "source target: " + item.target + "\nprobe: " + item.probe + "\n\nSuggested filters:\n"
            + ("\n".join(filters) or "<нет>")
            + "\n\nStrategy inserted into profile:\n"
            + "\n".join(strategy)
        )
        apply_button.setEnabled(state.get("process") is None)

    def stop_process(owner: bool = False, reason: str = "") -> None:
        process = state.get("process")
        if process is None:
            return
        if owner:
            state["owner_stop"] = True
        if reason:
            state["auto_reason"] = reason
        process.terminate()
        QtCore.QTimer.singleShot(3000, lambda: process.kill() if state.get("process") is process else None)

    def start_target() -> None:
        index = int(state["target_index"])
        target_list = list(state["targets"])
        if index >= len(target_list):
            status.setText("AVAILABLE не найден ни для одного target")
            set_running(False)
            return
        target = str(target_list[index])
        enable_http, enable_tls12, enable_tls13, enable_quic = _blockcheck_modes(profile)
        options = BlockcheckOptions(
            domains=target,
            service_target_preset_id=SERVICE_TARGET_CUSTOM,
            scan_mode=BLOCKCHECK_SCAN_STOP_AFTER_FIRST_AVAILABLE,
            test="standard",
            scanlevel="quick",
            ipvs="4",
            enable_http=enable_http,
            enable_https_tls12=enable_tls12,
            enable_https_tls13=enable_tls13,
            enable_http3=enable_quic,
            skip_dnscheck=True,
            repeats=1,
            curl_max_time=3,
            timeout_seconds=0,
            dead_target_guard=BLOCKCHECK_DEAD_TARGET_GUARD_AUTO_STOP,
        )
        try:
            prepared = prepare_blockcheck_execution(root=root, options=options)
        except BlockcheckPreparationError as exc:
            output.setPlainText(exc.result.to_text())
            status.setText("Подготовка Blockcheck не прошла")
            set_running(False)
            return
        except Exception as exc:
            output.setPlainText(f"Blockcheck: ошибка подготовки\n{exc}")
            status.setText("Ошибка подготовки")
            set_running(False)
            return

        process = QtCore.QProcess(dialog)
        process.setProgram(prepared.command.argv[0])
        process.setArguments(list(prepared.command.argv[1:]))
        process.setWorkingDirectory(str(prepared.command.cwd))
        process.setProcessChannelMode(QtCore.QProcess.ProcessChannelMode.SeparateChannels)
        process_env = QtCore.QProcessEnvironment.systemEnvironment()
        for key, value in prepared.env.items():
            process_env.insert(str(key), str(value))
        process.setProcessEnvironment(process_env)

        state.update(
            {
                "process": process,
                "prepared": prepared,
                "stdout": [],
                "stderr": [],
                "monitor": BlockcheckPortPrecheckMonitor(target=target),
                "owner_stop": False,
                "auto_reason": "",
            }
        )
        append(f"\n===== target {index + 1}/{len(target_list)}: {target} =====")
        append(prepared.start_text())
        status.setText(f"Выполняется: {target}")
        set_running(True)
        write_blockcheck_last_log(prepared.command, "", "")

        def read_stdout() -> None:
            data = bytes(process.readAllStandardOutput()).decode("utf-8", errors="replace")
            state["stdout"].append(data)
            append(data)
            monitor = state.get("monitor")
            reason = monitor.feed_stdout(data) if monitor is not None else ""
            current = "".join(state["stdout"])
            found = parse_blockcheck_available_strategies(current)
            if found and not state.get("auto_reason"):
                stop_process(reason="AVAILABLE найден; compact run останавливается")
            elif reason and not state.get("auto_reason"):
                stop_process(reason=reason)

        def read_stderr() -> None:
            data = bytes(process.readAllStandardError()).decode("utf-8", errors="replace")
            state["stderr"].append(data)
            append(data)

        def process_error(error: Any) -> None:
            if state.get("owner_stop") or state.get("auto_reason"):
                return
            state["stderr"].append(f"\nQProcess error: {error}\n")

        def finished(exit_code: int, exit_status: Any) -> None:
            stdout = "".join(state["stdout"])
            stderr = "".join(state["stderr"])
            prepared_now = state.get("prepared")
            stats = parse_blockcheck_run_stats(stdout, stderr)
            found = list(parse_blockcheck_available_strategies(stdout))
            footer = (
                f"return code: {exit_code}\nexit status: {exit_status}\n"
                f"owner stop: {'yes' if state.get('owner_stop') else 'no'}\n"
                f"auto reason: {state.get('auto_reason') or 'нет'}\n\n{stats.to_text()}"
            )
            append("\n===== FINISHED =====\n" + footer)
            if prepared_now is not None:
                write_blockcheck_last_log(prepared_now.command, stdout, stderr, footer=footer)
            state["process"] = None
            state["prepared"] = None
            state["monitor"] = None

            if found:
                state["available"] = found
                candidates.clear()
                for item in found:
                    candidates.addItem(f"{item.probe} / {item.target}\n{item.command}")
                candidates.setCurrentRow(0)
                status.setText(f"Найдено AVAILABLE: {len(found)}")
                set_running(False)
                show_candidate()
                return
            if state.get("owner_stop"):
                status.setText("Остановлено владельцем")
                set_running(False)
                return
            state["target_index"] = int(state["target_index"]) + 1
            if int(state["target_index"]) < len(state["targets"]):
                QtCore.QTimer.singleShot(250, start_target)
            else:
                status.setText("AVAILABLE не найден")
                set_running(False)

        process.readyReadStandardOutput.connect(read_stdout)
        process.readyReadStandardError.connect(read_stderr)
        process.errorOccurred.connect(process_error)
        process.finished.connect(finished)
        process.start()

    def start() -> None:
        question = QtWidgets.QMessageBox.question(
            dialog,
            "Blockcheck → профиль",
            "Запустить upstream blockcheck2.sh через sudo -A?\n\n"
            "На время проверки выключите Default workflow, VPN и другие DPI-bypass процессы. "
            "Blockcheck временно меняет firewall redirect и выполняет cleanup. Пароль приложение не сохраняет.",
        )
        if question != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        state["target_index"] = 0
        output.clear()
        candidates.clear()
        preview.clear()
        state["available"] = []
        start_target()

    def apply() -> None:
        item = selected_candidate()
        if item is None:
            return
        state["result"] = split_blockcheck_profile_args(item.runtime_args)
        dialog.accept()

    def close() -> None:
        if state.get("process") is not None:
            return
        dialog.reject()

    start_button.clicked.connect(start)
    stop_button.clicked.connect(lambda _checked=False: stop_process(owner=True))
    apply_button.clicked.connect(apply)
    close_button.clicked.connect(close)
    candidates.currentRowChanged.connect(lambda _row: show_candidate())

    result = dialog.exec()
    if _accepted(QtWidgets, result):
        return state.get("result")
    return None


def edit_traffic_profile_dialog(
    parent: Any,
    root: Path | None,
    initial: EditableTrafficProfile | None = None,
) -> EditableTrafficProfile | None:
    QtCore, QtWidgets = require_pyqt()
    templates = list_profile_strategy_templates(root)
    draft = initial or EditableTrafficProfile(
        name="Новый профиль",
        protocol=PRESET_PROTOCOL_TCP,
        ports="443",
        l7="tls",
        target_kind=PRESET_TARGET_DOMAINS,
        target_value="",
        strategy_args=("--payload=tls_client_hello", "--lua-desync=multidisorder:pos=1,midsld"),
    )

    dialog = QtWidgets.QDialog(parent)
    dialog.setWindowTitle("Профиль пресета")
    dialog.resize(840, 720)
    layout = QtWidgets.QVBoxLayout(dialog)

    form_box = QtWidgets.QGroupBox("Filter и target")
    form = QtWidgets.QFormLayout(form_box)
    name_edit = QtWidgets.QLineEdit(draft.name)
    enabled_check = QtWidgets.QCheckBox("Профиль включён")
    enabled_check.setChecked(draft.enabled)
    protocol_combo = QtWidgets.QComboBox()
    protocol_combo.addItem("TCP", PRESET_PROTOCOL_TCP)
    protocol_combo.addItem("UDP", PRESET_PROTOCOL_UDP)
    protocol_combo.addItem("Any IP protocol", PRESET_PROTOCOL_ANY)
    protocol_combo.setCurrentIndex(max(0, protocol_combo.findData(draft.protocol)))
    ports_edit = QtWidgets.QLineEdit(draft.ports)
    ports_edit.setPlaceholderText("443 или 50000-65535")
    l3_edit = QtWidgets.QLineEdit(draft.l3)
    l3_edit.setPlaceholderText("ipv4,ipv6 — необязательно")
    l7_edit = QtWidgets.QLineEdit(draft.l7)
    l7_edit.setPlaceholderText("tls, http, quic, stun, discord — необязательно")
    target_combo = QtWidgets.QComboBox()
    target_combo.addItem("Домены / URI", PRESET_TARGET_DOMAINS)
    target_combo.addItem("Hostlist file", PRESET_TARGET_HOSTLIST)
    target_combo.addItem("IP / CIDR inline", PRESET_TARGET_IPS)
    target_combo.addItem("IPSet file", PRESET_TARGET_IPSET)
    target_combo.addItem("Без target", PRESET_TARGET_NONE)
    target_combo.setCurrentIndex(max(0, target_combo.findData(draft.target_kind)))
    target_edit = QtWidgets.QPlainTextEdit(draft.target_value)
    target_edit.setMaximumHeight(90)

    form.addRow("Имя", name_edit)
    form.addRow("Состояние", enabled_check)
    form.addRow("Протокол", protocol_combo)
    form.addRow("Порты", ports_edit)
    form.addRow("L3", l3_edit)
    form.addRow("L7", l7_edit)
    form.addRow("Тип цели", target_combo)
    form.addRow("Цель", target_edit)
    layout.addWidget(form_box)

    strategy_box = QtWidgets.QGroupBox("Стратегия профиля")
    strategy_layout = QtWidgets.QVBoxLayout(strategy_box)
    mode_combo = QtWidgets.QComboBox()
    mode_combo.addItem("Известная стратегия", "known")
    mode_combo.addItem("Ручные nfqws2 args", "manual")
    template_combo = QtWidgets.QComboBox()
    template_combo.setMinimumContentsLength(50)
    for item in templates:
        template_combo.addItem(item.title, item.template_id)
    manual_edit = QtWidgets.QPlainTextEdit(strategy_args_to_text(draft.strategy_args))
    manual_edit.setLineWrapMode(QtWidgets.QPlainTextEdit.LineWrapMode.NoWrap)
    manual_edit.setMinimumHeight(180)
    blockcheck_button = QtWidgets.QPushButton("Подобрать Blockcheck и вставить")
    blockcheck_hint = QtWidgets.QLabel(
        "Blockcheck доступен для domain targets. Для Discord Voice/IP/UDP нужен отдельный probe; здесь остаются известная или ручная стратегия."
    )
    blockcheck_hint.setWordWrap(True)
    strategy_layout.addWidget(mode_combo)
    strategy_layout.addWidget(template_combo)
    strategy_layout.addWidget(manual_edit, 1)
    strategy_layout.addWidget(blockcheck_button)
    strategy_layout.addWidget(blockcheck_hint)
    layout.addWidget(strategy_box, 1)

    buttons = QtWidgets.QDialogButtonBox(
        QtWidgets.QDialogButtonBox.StandardButton.Save | QtWidgets.QDialogButtonBox.StandardButton.Cancel
    )
    layout.addWidget(buttons)

    exact_template = next((item for item in templates if item.strategy_args == draft.strategy_args), None)
    if exact_template is not None:
        index = template_combo.findData(exact_template.template_id)
        if index >= 0:
            template_combo.setCurrentIndex(index)
        mode_combo.setCurrentIndex(0)
    else:
        mode_combo.setCurrentIndex(1)

    def current_template() -> ProfileStrategyTemplate | None:
        template_id = str(template_combo.currentData() or "")
        return next((item for item in templates if item.template_id == template_id), None)

    def sync_mode() -> None:
        known = str(mode_combo.currentData()) == "known"
        template_combo.setVisible(known)
        manual_edit.setVisible(not known)

    def sync_protocol() -> None:
        ports_edit.setEnabled(str(protocol_combo.currentData()) != PRESET_PROTOCOL_ANY)

    def sync_target() -> None:
        kind = str(target_combo.currentData())
        target_edit.setEnabled(kind != PRESET_TARGET_NONE)
        blockcheck_button.setEnabled(kind == PRESET_TARGET_DOMAINS)
        if kind == PRESET_TARGET_DOMAINS:
            target_edit.setPlaceholderText("youtube.com www.youtube.com")
        elif kind == PRESET_TARGET_HOSTLIST:
            target_edit.setPlaceholderText("profiles/hostlists/default.hosts")
        elif kind == PRESET_TARGET_IPS:
            target_edit.setPlaceholderText("162.159.128.233 162.159.0.0/16")
        elif kind == PRESET_TARGET_IPSET:
            target_edit.setPlaceholderText("profiles/ipsets/discord.txt")
        else:
            target_edit.setPlaceholderText("")

    def collect(*, validate: bool = True) -> EditableTrafficProfile:
        if str(mode_combo.currentData()) == "known":
            template = current_template()
            if template is None:
                raise ValueError("Каталог известных profile strategies пуст")
            strategy_args = template.strategy_args
            if not l7_edit.text().strip() and template.suggested_l7:
                l7_edit.setText(",".join(template.suggested_l7))
        else:
            if validate:
                strategy_args = parse_manual_strategy_text(manual_edit.toPlainText())
            else:
                try:
                    strategy_args = parse_manual_strategy_text(manual_edit.toPlainText())
                except ValueError:
                    strategy_args = ("--lua-desync=multisplit:pos=1",)
        result = EditableTrafficProfile(
            name=name_edit.text().strip(),
            protocol=str(protocol_combo.currentData()),
            ports=ports_edit.text().strip(),
            l3=l3_edit.text().strip(),
            l7=l7_edit.text().strip(),
            target_kind=str(target_combo.currentData()),
            target_value=target_edit.toPlainText().strip(),
            strategy_args=strategy_args,
            enabled=enabled_check.isChecked(),
        )
        if validate:
            result.validate()
        return result

    def run_blockcheck() -> None:
        try:
            current = collect(validate=False)
            # Validate filter/target enough for Blockcheck, but use a temporary
            # minimal action if the current manual strategy is unfinished.
            if not current.strategy_args:
                current = EditableTrafficProfile(
                    name=current.name,
                    protocol=current.protocol,
                    ports=current.ports,
                    l3=current.l3,
                    l7=current.l7,
                    target_kind=current.target_kind,
                    target_value=current.target_value,
                    strategy_args=("--lua-desync=multisplit:pos=1",),
                    enabled=current.enabled,
                )
            current.validate()
        except Exception as exc:
            _message_error(QtWidgets, dialog, "Параметры профиля", str(exc))
            return
        selected = run_profile_blockcheck_dialog(dialog, root, current)
        if selected is None:
            return
        filters, strategy = selected
        for arg in filters:
            if arg.startswith("--filter-l7=") and not l7_edit.text().strip():
                l7_edit.setText(arg.partition("=")[2])
            elif arg.startswith("--filter-tcp=") and str(protocol_combo.currentData()) == PRESET_PROTOCOL_ANY:
                protocol_combo.setCurrentIndex(protocol_combo.findData(PRESET_PROTOCOL_TCP))
                ports_edit.setText(arg.partition("=")[2])
            elif arg.startswith("--filter-udp=") and str(protocol_combo.currentData()) == PRESET_PROTOCOL_ANY:
                protocol_combo.setCurrentIndex(protocol_combo.findData(PRESET_PROTOCOL_UDP))
                ports_edit.setText(arg.partition("=")[2])
        manual_edit.setPlainText(strategy_args_to_text(strategy))
        mode_combo.setCurrentIndex(mode_combo.findData("manual"))
        sync_mode()

    def save() -> None:
        try:
            dialog._result_profile = collect(validate=True)  # type: ignore[attr-defined]
        except Exception as exc:
            _message_error(QtWidgets, dialog, "Профиль не сохранён", str(exc))
            return
        dialog.accept()

    mode_combo.currentIndexChanged.connect(lambda _index: sync_mode())
    protocol_combo.currentIndexChanged.connect(lambda _index: sync_protocol())
    target_combo.currentIndexChanged.connect(lambda _index: sync_target())
    blockcheck_button.clicked.connect(run_blockcheck)
    buttons.accepted.connect(save)
    buttons.rejected.connect(dialog.reject)
    sync_mode()
    sync_protocol()
    sync_target()

    result = dialog.exec()
    if not _accepted(QtWidgets, result):
        return None
    return getattr(dialog, "_result_profile", None)
