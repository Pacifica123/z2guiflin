"""PyQt blockcheck lab page for manual strategy discovery."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from ..adapters.blockcheck_gui import (
    BLOCKCHECK_SCAN_ALL_TARGETS,
    BLOCKCHECK_SCAN_SKIP_DEAD_ONLY,
    BLOCKCHECK_SCAN_STOP_AFTER_FIRST_AVAILABLE,
    BlockcheckOptions,
    BlockcheckPortPrecheckMonitor,
    BlockcheckPreparationError,
    PreparedBlockcheckExecution,
    blockcheck_build_plan_to_text,
    blockcheck_coverage_to_text,
    blockcheck_service_policy_to_text,
    blockcheck_tournament_to_text,
    blockcheck_plan_to_text,
    blockcheck_preflight_to_text,
    execute_blockcheck_prereq_build,
    export_blockcheck_available_strategies,
    last_blockcheck_log_to_text,
    parse_blockcheck_run_stats,
    parse_blockcheck_summary,
    prepare_blockcheck_execution,
    write_blockcheck_last_log,
)
from ..adapters.discord_verification import discord_non_voice_verification_plan_to_text
from ..models.service_targets import (
    DEFAULT_BLOCKCHECK_TARGET_STRING,
    SERVICE_TARGET_CUSTOM,
    SERVICE_TARGET_DISCORD_DESKTOP,
    get_service_target_preset,
    service_target_recommended_scan_mode,
    list_service_target_presets,
)
from ..qt_compat import require_pyqt


def make_blockcheck_lab_page(root: Path | None = None) -> Any:
    """Create a GUI page that wraps upstream blockcheck2.sh explicitly."""

    QtCore, QtWidgets = require_pyqt()
    page = QtWidgets.QWidget()
    layout = QtWidgets.QVBoxLayout(page)
    layout.setContentsMargins(14, 14, 14, 14)
    layout.setSpacing(10)

    title = QtWidgets.QLabel("Диагностика: Blockcheck lab")
    title.setObjectName("pageTitle")
    intro = QtWidgets.QLabel(
        "Здесь можно вручную прогнать upstream blockcheck2.sh для домена YouTube или другого target, "
        "посмотреть найденные стратегии и затем одной кнопкой сгенерировать strategy-файлы в strategies/generated. "
        "Запуск требует sudo, временно меняет firewall redirect внутри blockcheck и должен выполняться при выключенном Default workflow/VPN. "
        "Долгий run идёт в фоне: окно остаётся живым, лог дописывается потоком, остановка выполняется отдельной кнопкой."
    )
    intro.setWordWrap(True)

    form_box = QtWidgets.QGroupBox("Параметры scan")
    form = QtWidgets.QGridLayout(form_box)
    form.setHorizontalSpacing(8)
    form.setVerticalSpacing(8)

    target_preset_combo = QtWidgets.QComboBox()
    target_preset_combo.setObjectName("blockcheckServiceTargetPreset")
    for preset in list_service_target_presets():
        target_preset_combo.addItem(preset.title, preset.preset_id)

    target_preset_hint = QtWidgets.QLabel("")
    target_preset_hint.setObjectName("mutedText")
    target_preset_hint.setWordWrap(True)

    domains_edit = QtWidgets.QLineEdit(DEFAULT_BLOCKCHECK_TARGET_STRING)
    domains_edit.setObjectName("blockcheckDomainsEdit")
    domains_edit.setPlaceholderText(DEFAULT_BLOCKCHECK_TARGET_STRING)

    scan_mode_combo = QtWidgets.QComboBox()
    scan_mode_combo.setObjectName("blockcheckCandidateScanMode")
    scan_mode_combo.addItem("Stop after first AVAILABLE", BLOCKCHECK_SCAN_STOP_AFTER_FIRST_AVAILABLE)
    scan_mode_combo.addItem("Scan all preset targets", BLOCKCHECK_SCAN_ALL_TARGETS)
    scan_mode_combo.addItem("Skip only dead targets", BLOCKCHECK_SCAN_SKIP_DEAD_ONLY)

    test_combo = QtWidgets.QComboBox()
    test_combo.addItems(["standard", "custom"])

    scan_combo = QtWidgets.QComboBox()
    scan_combo.addItems(["quick", "standard", "force"])

    ip_combo = QtWidgets.QComboBox()
    ip_combo.addItems(["4", "6", "46"])

    repeats_spin = QtWidgets.QSpinBox()
    repeats_spin.setRange(1, 5)
    repeats_spin.setValue(1)

    timeout_spin = QtWidgets.QSpinBox()
    timeout_spin.setRange(1, 15)
    timeout_spin.setValue(3)
    timeout_spin.setSuffix(" сек")

    http_check = QtWidgets.QCheckBox("HTTP")
    https12_check = QtWidgets.QCheckBox("HTTPS TLS1.2")
    https13_check = QtWidgets.QCheckBox("HTTPS TLS1.3")
    http3_check = QtWidgets.QCheckBox("HTTP/3 QUIC")
    dns_check = QtWidgets.QCheckBox("DNS precheck")
    http_check.setChecked(False)
    https12_check.setChecked(True)
    https13_check.setChecked(True)
    http3_check.setChecked(True)
    dns_check.setChecked(False)

    form.addWidget(QtWidgets.QLabel("Service target"), 0, 0)
    form.addWidget(target_preset_combo, 0, 1, 1, 3)
    form.addWidget(target_preset_hint, 1, 1, 1, 3)
    form.addWidget(QtWidgets.QLabel("Домены/URI"), 2, 0)
    form.addWidget(domains_edit, 2, 1, 1, 3)
    form.addWidget(QtWidgets.QLabel("Candidate mode"), 3, 0)
    form.addWidget(scan_mode_combo, 3, 1, 1, 3)
    form.addWidget(QtWidgets.QLabel("Набор"), 4, 0)
    form.addWidget(test_combo, 4, 1)
    form.addWidget(QtWidgets.QLabel("Scanlevel"), 4, 2)
    form.addWidget(scan_combo, 4, 3)
    form.addWidget(QtWidgets.QLabel("IP"), 5, 0)
    form.addWidget(ip_combo, 5, 1)
    form.addWidget(QtWidgets.QLabel("Repeats"), 5, 2)
    form.addWidget(repeats_spin, 5, 3)
    form.addWidget(QtWidgets.QLabel("Curl timeout"), 6, 0)
    form.addWidget(timeout_spin, 6, 1)
    form.addWidget(http_check, 7, 0)
    form.addWidget(https12_check, 7, 1)
    form.addWidget(https13_check, 7, 2)
    form.addWidget(http3_check, 7, 3)
    form.addWidget(dns_check, 8, 0, 1, 2)

    buttons = QtWidgets.QHBoxLayout()
    preflight_button = QtWidgets.QPushButton("Preflight")
    build_plan_button = QtWidgets.QPushButton("План binaries")
    build_button = QtWidgets.QPushButton("Собрать binaries")
    plan_button = QtWidgets.QPushButton("План run")
    run_button = QtWidgets.QPushButton("Запустить blockcheck")
    stop_button = QtWidgets.QPushButton("Остановить")
    export_button = QtWidgets.QPushButton("Создать стратегии")
    coverage_button = QtWidgets.QPushButton("Coverage")
    policy_button = QtWidgets.QPushButton("Policy")
    tournament_button = QtWidgets.QPushButton("Tournament")
    verify_button = QtWidgets.QPushButton("Discord checklist")
    log_button = QtWidgets.QPushButton("Последний лог")
    stop_button.setEnabled(False)
    buttons.addWidget(preflight_button)
    buttons.addWidget(build_plan_button)
    buttons.addWidget(build_button)
    buttons.addWidget(plan_button)
    buttons.addWidget(run_button)
    buttons.addWidget(stop_button)
    buttons.addWidget(export_button)
    buttons.addWidget(coverage_button)
    buttons.addWidget(policy_button)
    buttons.addWidget(tournament_button)
    buttons.addWidget(verify_button)
    buttons.addWidget(log_button)
    buttons.addStretch(1)

    status = QtWidgets.QLabel("Статус: idle")
    status.setObjectName("mutedText")

    output = QtWidgets.QPlainTextEdit()
    output.setReadOnly(True)
    output.setMinimumHeight(300)
    try:
        output.setLineWrapMode(QtWidgets.QPlainTextEdit.LineWrapMode.WidgetWidth)
    except Exception:  # pragma: no cover - compatibility with older Qt bindings
        pass
    output.setPlainText(blockcheck_preflight_to_text(root=root))

    state: dict[str, Any] = {
        "process": None,
        "prepared": None,
        "stdout": [],
        "stderr": [],
        "stopped_by_user": False,
        "auto_skip_reason": "",
        "monitor": None,
        "candidate_targets": [],
        "candidate_index": 0,
        "active_target_preset": str(target_preset_combo.currentData()),
        "custom_targets": "",
        "syncing_target_preset": False,
    }

    def selected_target_preset_id() -> str:
        preset_id = target_preset_combo.currentData()
        return str(preset_id or "")

    def apply_target_preset(preset_id: str, *, remember_previous_custom: bool = True) -> None:
        if state.get("syncing_target_preset"):
            return
        previous = str(state.get("active_target_preset") or "")
        if remember_previous_custom and previous == SERVICE_TARGET_CUSTOM:
            state["custom_targets"] = domains_edit.text().strip()
        preset = get_service_target_preset(preset_id)
        state["syncing_target_preset"] = True
        try:
            state["active_target_preset"] = preset.preset_id
            target_preset_hint.setText(f"{preset.preset_id}: {preset.summary}")
            recommended_scan_mode = service_target_recommended_scan_mode(preset.preset_id)
            index = scan_mode_combo.findData(recommended_scan_mode)
            if index >= 0 and preset.preset_id != SERVICE_TARGET_CUSTOM:
                scan_mode_combo.setCurrentIndex(index)
            if preset.is_custom:
                domains_edit.setReadOnly(False)
                domains_edit.setPlaceholderText("example.com api.example.com")
                custom_targets = str(state.get("custom_targets") or "").strip()
                if custom_targets:
                    domains_edit.setText(custom_targets)
            else:
                domains_edit.setReadOnly(True)
                domains_edit.setPlaceholderText(preset.target_string)
                domains_edit.setText(preset.target_string)
        finally:
            state["syncing_target_preset"] = False

    def collect_options() -> BlockcheckOptions:
        return BlockcheckOptions(
            domains=domains_edit.text().strip(),
            service_target_preset_id=selected_target_preset_id(),
            scan_mode=str(scan_mode_combo.currentData() or BLOCKCHECK_SCAN_STOP_AFTER_FIRST_AVAILABLE),
            test=str(test_combo.currentText()),
            scanlevel=str(scan_combo.currentText()),
            ipvs=str(ip_combo.currentText()),
            enable_http=http_check.isChecked(),
            enable_https_tls12=https12_check.isChecked(),
            enable_https_tls13=https13_check.isChecked(),
            enable_http3=http3_check.isChecked(),
            skip_dnscheck=not dns_check.isChecked(),
            repeats=int(repeats_spin.value()),
            curl_max_time=int(timeout_spin.value()),
            timeout_seconds=0,
        )

    def append_output(text: str) -> None:
        if not text:
            return
        output.appendPlainText(text.rstrip("\n"))
        scrollbar = output.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def current_prepared() -> PreparedBlockcheckExecution | None:
        prepared = state.get("prepared")
        return prepared if isinstance(prepared, PreparedBlockcheckExecution) else None

    def flush_live_log() -> None:
        prepared = current_prepared()
        if prepared is None:
            return
        write_blockcheck_last_log(
            prepared.command,
            "".join(state["stdout"]),
            "".join(state["stderr"]),
        )

    def set_running(running: bool) -> None:
        target_preset_combo.setEnabled(not running)
        scan_mode_combo.setEnabled(not running)
        domains_edit.setEnabled(not running)
        for button in (preflight_button, build_plan_button, build_button, plan_button, run_button, export_button, coverage_button, policy_button, tournament_button, verify_button, log_button):
            button.setEnabled(not running)
        stop_button.setEnabled(running)
        if running:
            targets = state.get("candidate_targets") or []
            index = int(state.get("candidate_index") or 0)
            if targets:
                status.setText(f"Статус: blockcheck candidate {index + 1}/{len(targets)} выполняется…")
            else:
                status.setText("Статус: blockcheck выполняется…")
        else:
            status.setText("Статус: idle")

    def run_action(label: str, func: Callable[[], str]) -> None:
        if state.get("process") is not None:
            output.setPlainText("Blockcheck уже выполняется. Сначала остановите текущий run или дождитесь завершения.")
            return
        try:
            output.setPlainText(func())
        except Exception as exc:  # pragma: no cover - GUI diagnostic path
            output.setPlainText(f"{label}: ошибка\n{exc}")

    def build_binaries() -> None:
        if state.get("process") is not None:
            output.setPlainText("Blockcheck уже выполняется. Сначала остановите текущий run или дождитесь завершения.")
            return
        question = QtWidgets.QMessageBox.question(
            page,
            "Blockcheck prerequisites",
            (
                "Собрать локальные prerequisites для blockcheck через make all?\n\n"
                "Это не требует sudo, не запускает install scripts и не меняет firewall/services, "
                "но создаёт build artifacts внутри core/zapret2: nfqws2, mdig и ip2net."
            ),
        )
        if question != QtWidgets.QMessageBox.StandardButton.Yes:
            output.setPlainText("Blockcheck prerequisites build: отменено пользователем")
            return
        run_action("Blockcheck prerequisites build", lambda: execute_blockcheck_prereq_build(root=root).to_text())

    def start_next_candidate() -> None:
        targets = list(state.get("candidate_targets") or [])
        index = int(state.get("candidate_index") or 0)
        if index >= len(targets):
            append_output("\n[GUI] Sequential Blockcheck candidates finished.")
            state["candidate_targets"] = []
            state["candidate_index"] = 0
            set_running(False)
            return

        target = str(targets[index])
        base_options = collect_options()
        try:
            prepared = prepare_blockcheck_execution(root=root, options=base_options.for_single_domain(target))
        except BlockcheckPreparationError as exc:
            output.setPlainText(exc.result.to_text())
            state["candidate_targets"] = []
            state["candidate_index"] = 0
            set_running(False)
            return
        except Exception as exc:  # pragma: no cover - GUI diagnostic path
            output.setPlainText(f"Blockcheck run: ошибка подготовки candidate {target}\n{exc}")
            state["candidate_targets"] = []
            state["candidate_index"] = 0
            set_running(False)
            return

        append_output(f"\n[GUI] Starting candidate {index + 1}/{len(targets)}: {target}")
        start_prepared_process(prepared, clear_output=False)

    def finalize_process(exit_code: int, exit_status: Any) -> None:
        prepared = current_prepared()
        stdout = "".join(state["stdout"])
        stderr = "".join(state["stderr"])
        stopped = bool(state.get("stopped_by_user"))
        auto_skip_reason = str(state.get("auto_skip_reason") or "")
        if stopped:
            stderr += "\n[GUI] Blockcheck process was stopped by owner.\n"
            state["stderr"] = [stderr]
        elif auto_skip_reason:
            stderr += f"\n[GUI] Blockcheck candidate auto-stopped: {auto_skip_reason}\n"
            state["stderr"] = [stderr]
        stats = parse_blockcheck_run_stats(stdout, stderr)
        summary = parse_blockcheck_summary(stdout)
        footer = [
            "",
            "===== FINISHED =====",
            f"return code: {exit_code}",
            f"exit status: {exit_status}",
            f"stopped by owner: {'yes' if stopped else 'no'}",
            f"auto skipped dead target: {'yes' if auto_skip_reason else 'no'}",
        ]
        if auto_skip_reason:
            footer.append(f"auto skip reason: {auto_skip_reason}")
        if prepared is not None:
            footer.append(f"log path: {prepared.command.log_path or 'не задан'}")
        if stats.has_observations:
            footer.extend(["", stats.to_text()])
        if summary:
            footer.extend(["", "Parsed SUMMARY / working strategy hints:"])
            footer.extend(f"- {line}" for line in summary)
        footer_text = "\n".join(footer)
        append_output(footer_text)
        if prepared is not None:
            write_blockcheck_last_log(prepared.command, stdout, stderr, footer=footer_text)

        state["process"] = None
        state["prepared"] = None
        state["monitor"] = None
        state["stopped_by_user"] = False
        state["auto_skip_reason"] = ""

        targets = list(state.get("candidate_targets") or [])
        current_index = int(state.get("candidate_index") or 0)
        next_exists = current_index + 1 < len(targets)
        scan_mode = prepared.command.options.scan_mode if prepared is not None else BLOCKCHECK_SCAN_STOP_AFTER_FIRST_AVAILABLE
        should_continue = False
        if not stopped and next_exists:
            if scan_mode == BLOCKCHECK_SCAN_ALL_TARGETS:
                should_continue = True
            elif scan_mode == BLOCKCHECK_SCAN_STOP_AFTER_FIRST_AVAILABLE:
                should_continue = stats.available == 0
            elif scan_mode == BLOCKCHECK_SCAN_SKIP_DEAD_ONLY:
                should_continue = bool(auto_skip_reason)
        if should_continue:
            state["candidate_index"] = current_index + 1
            status.setText("Статус: переход к следующему candidate…")
            QtCore.QTimer.singleShot(250, start_next_candidate)
            return

        state["candidate_targets"] = []
        state["candidate_index"] = 0
        set_running(False)

    def handle_process_error(error: Any) -> None:
        if state.get("stopped_by_user") or state.get("auto_skip_reason"):
            # Qt reports a SIGTERM/SIGKILL stopped process as CrashExit. For an
            # explicit owner Stop or an evidence-based dead-target skip this is
            # expected and the final footer records the reason.
            return
        text = f"\n[GUI] QProcess error: {error}"
        state["stderr"].append(text)
        append_output(text)
        flush_live_log()

    def start_prepared_process(prepared: PreparedBlockcheckExecution, *, clear_output: bool = True) -> None:
        process = QtCore.QProcess(page)
        process.setProgram(prepared.command.argv[0])
        process.setArguments(list(prepared.command.argv[1:]))
        process.setWorkingDirectory(str(prepared.command.cwd))
        process.setProcessChannelMode(QtCore.QProcess.ProcessChannelMode.SeparateChannels)
        process_env = QtCore.QProcessEnvironment.systemEnvironment()
        for key, value in prepared.env.items():
            process_env.insert(str(key), str(value))
        process.setProcessEnvironment(process_env)

        target = prepared.command.options.normalized_domains()[0]
        monitor = BlockcheckPortPrecheckMonitor(target=target)

        def request_auto_skip(reason: str) -> None:
            if state.get("auto_skip_reason") or state.get("stopped_by_user"):
                return
            state["auto_skip_reason"] = reason
            message = (
                "\n[GUI] Evidence-based early stop: "
                f"{reason}. Moving to the next candidate if one exists.\n"
            )
            state["stderr"].append(message)
            append_output(message)
            status.setText("Статус: dead target detected; stopping candidate…")
            process.terminate()
            QtCore.QTimer.singleShot(3000, lambda: process.kill() if state.get("process") is process else None)

        def read_stdout() -> None:
            data = bytes(process.readAllStandardOutput()).decode("utf-8", errors="replace")
            state["stdout"].append(data)
            append_output(data)
            status.setText(f"Статус: running; stdout {len(''.join(state['stdout'])) // 1024} KiB")
            reason = monitor.feed_stdout(data)
            if reason:
                request_auto_skip(reason)
            flush_live_log()

        def read_stderr() -> None:
            data = bytes(process.readAllStandardError()).decode("utf-8", errors="replace")
            state["stderr"].append(data)
            append_output(data)
            flush_live_log()

        process.readyReadStandardOutput.connect(read_stdout)
        process.readyReadStandardError.connect(read_stderr)
        process.finished.connect(finalize_process)
        process.errorOccurred.connect(handle_process_error)

        state["process"] = process
        state["prepared"] = prepared
        state["stdout"] = []
        state["stderr"] = []
        state["stopped_by_user"] = False
        state["auto_skip_reason"] = ""
        state["monitor"] = monitor
        if clear_output:
            output.setPlainText(prepared.start_text())
        else:
            append_output("\n" + prepared.start_text())
        write_blockcheck_last_log(prepared.command, "", "")
        set_running(True)
        process.start()

    def run_blockcheck() -> None:
        if state.get("process") is not None:
            output.setPlainText("Blockcheck уже выполняется. Сначала остановите текущий run или дождитесь завершения.")
            return
        question = QtWidgets.QMessageBox.question(
            page,
            "Blockcheck lab",
            (
                "Запустить upstream blockcheck2.sh через графический sudo prompt?\n\n"
                "Targets будут проверяться последовательно. Если port precheck текущего target даст 0 connects / N failed, "
                "GUI остановит только этот candidate и перейдёт к следующему, не сжигая сотни strategy checks впустую. "
                "Рекомендуется сначала выключить Default workflow, VPN и другие DPI-bypass процессы. "
                "Blockcheck временно меняет firewall redirect и затем очищает его через свой cleanup. "
                "Пароль не сохраняется приложением. Общий таймер не ставится: лог будет идти в окно, "
                "а остановка выполняется кнопкой Stop."
            ),
        )
        if question != QtWidgets.QMessageBox.StandardButton.Yes:
            output.setPlainText("Blockcheck run: отменено пользователем")
            return
        try:
            targets = list(collect_options().ordered_domains_for_policy())
        except Exception as exc:
            output.setPlainText(f"Blockcheck run: ошибка параметров\n{exc}")
            return
        state["candidate_targets"] = targets
        state["candidate_index"] = 0
        output.setPlainText(
            "Sequential Blockcheck run\n"
            f"candidates: {', '.join(targets)}\n"
            f"candidate mode: {scan_mode_combo.currentData()}\n"
            "dead-target guard: enabled; evidence-based, no wall-clock timeout"
        )
        start_next_candidate()

    def stop_blockcheck() -> None:
        process = state.get("process")
        if process is None:
            return
        state["stopped_by_user"] = True
        append_output("\n[GUI] Stop requested by owner; sending terminate() to blockcheck process…")
        status.setText("Статус: stop requested…")
        process.terminate()
        QtCore.QTimer.singleShot(3000, lambda: process.kill() if state.get("process") is process else None)

    target_preset_combo.currentIndexChanged.connect(
        lambda _index=0: apply_target_preset(selected_target_preset_id())
    )
    apply_target_preset(selected_target_preset_id(), remember_previous_custom=False)

    preflight_button.clicked.connect(lambda _checked=False: run_action("Preflight", lambda: blockcheck_preflight_to_text(root=root)))
    build_plan_button.clicked.connect(lambda _checked=False: run_action("План binaries", lambda: blockcheck_build_plan_to_text(root=root)))
    build_button.clicked.connect(lambda _checked=False: build_binaries())
    plan_button.clicked.connect(lambda _checked=False: run_action("План run", lambda: blockcheck_plan_to_text(root=root, options=collect_options())))
    run_button.clicked.connect(lambda _checked=False: run_blockcheck())
    stop_button.clicked.connect(lambda _checked=False: stop_blockcheck())
    export_button.clicked.connect(lambda _checked=False: run_action("Создать стратегии", lambda: export_blockcheck_available_strategies(root=root).to_text()))
    coverage_button.clicked.connect(lambda _checked=False: run_action("Coverage", lambda: blockcheck_coverage_to_text(root=root)))
    policy_button.clicked.connect(lambda _checked=False: run_action("Policy", lambda: blockcheck_service_policy_to_text(selected_target_preset_id())))
    tournament_button.clicked.connect(lambda _checked=False: run_action("Tournament", lambda: blockcheck_tournament_to_text(root=root, preset_id=selected_target_preset_id())))
    verify_button.clicked.connect(lambda _checked=False: run_action("Discord checklist", lambda: discord_non_voice_verification_plan_to_text(root=root)))
    log_button.clicked.connect(lambda _checked=False: run_action("Последний лог", lambda: last_blockcheck_log_to_text(root=root)))

    layout.addWidget(title)
    layout.addWidget(intro)
    layout.addWidget(form_box)
    layout.addLayout(buttons)
    layout.addWidget(status)
    layout.addWidget(output, 1)
    return page
