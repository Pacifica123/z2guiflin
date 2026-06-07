"""PyQt blockcheck lab page for manual strategy discovery."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from ..adapters.blockcheck_gui import (
    BlockcheckOptions,
    BlockcheckPreparationError,
    PreparedBlockcheckExecution,
    blockcheck_build_plan_to_text,
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

    domains_edit = QtWidgets.QLineEdit("youtube.com www.youtube.com")
    domains_edit.setPlaceholderText("youtube.com www.youtube.com")

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

    form.addWidget(QtWidgets.QLabel("Домены/URI"), 0, 0)
    form.addWidget(domains_edit, 0, 1, 1, 3)
    form.addWidget(QtWidgets.QLabel("Набор"), 1, 0)
    form.addWidget(test_combo, 1, 1)
    form.addWidget(QtWidgets.QLabel("Scanlevel"), 1, 2)
    form.addWidget(scan_combo, 1, 3)
    form.addWidget(QtWidgets.QLabel("IP"), 2, 0)
    form.addWidget(ip_combo, 2, 1)
    form.addWidget(QtWidgets.QLabel("Repeats"), 2, 2)
    form.addWidget(repeats_spin, 2, 3)
    form.addWidget(QtWidgets.QLabel("Curl timeout"), 3, 0)
    form.addWidget(timeout_spin, 3, 1)
    form.addWidget(http_check, 4, 0)
    form.addWidget(https12_check, 4, 1)
    form.addWidget(https13_check, 4, 2)
    form.addWidget(http3_check, 4, 3)
    form.addWidget(dns_check, 5, 0, 1, 2)

    buttons = QtWidgets.QHBoxLayout()
    preflight_button = QtWidgets.QPushButton("Preflight")
    build_plan_button = QtWidgets.QPushButton("План binaries")
    build_button = QtWidgets.QPushButton("Собрать binaries")
    plan_button = QtWidgets.QPushButton("План run")
    run_button = QtWidgets.QPushButton("Запустить blockcheck")
    stop_button = QtWidgets.QPushButton("Остановить")
    export_button = QtWidgets.QPushButton("Создать стратегии")
    log_button = QtWidgets.QPushButton("Последний лог")
    stop_button.setEnabled(False)
    buttons.addWidget(preflight_button)
    buttons.addWidget(build_plan_button)
    buttons.addWidget(build_button)
    buttons.addWidget(plan_button)
    buttons.addWidget(run_button)
    buttons.addWidget(stop_button)
    buttons.addWidget(export_button)
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
    }

    def collect_options() -> BlockcheckOptions:
        return BlockcheckOptions(
            domains=domains_edit.text().strip(),
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
        for button in (preflight_button, build_plan_button, build_button, plan_button, run_button, export_button, log_button):
            button.setEnabled(not running)
        stop_button.setEnabled(running)
        status.setText("Статус: blockcheck выполняется…" if running else "Статус: idle")

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

    def finalize_process(exit_code: int, exit_status: Any) -> None:
        prepared = current_prepared()
        stdout = "".join(state["stdout"])
        stderr = "".join(state["stderr"])
        stopped = bool(state.get("stopped_by_user"))
        if stopped:
            stderr += "\n[GUI] Blockcheck process was stopped by owner.\n"
            state["stderr"] = [stderr]
        stats = parse_blockcheck_run_stats(stdout, stderr)
        summary = parse_blockcheck_summary(stdout)
        footer = [
            "",
            "===== FINISHED =====",
            f"return code: {exit_code}",
            f"exit status: {exit_status}",
            f"stopped by owner: {'yes' if stopped else 'no'}",
        ]
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
        state["stopped_by_user"] = False
        set_running(False)

    def handle_process_error(error: Any) -> None:
        if state.get("stopped_by_user"):
            # Qt reports a SIGTERM/SIGKILL stopped process as CrashExit. For an
            # explicit owner Stop this is expected and the final footer already
            # records that the run was stopped intentionally.
            return
        text = f"\n[GUI] QProcess error: {error}"
        state["stderr"].append(text)
        append_output(text)
        flush_live_log()

    def start_prepared_process(prepared: PreparedBlockcheckExecution) -> None:
        process = QtCore.QProcess(page)
        process.setProgram(prepared.command.argv[0])
        process.setArguments(list(prepared.command.argv[1:]))
        process.setWorkingDirectory(str(prepared.command.cwd))
        process.setProcessChannelMode(QtCore.QProcess.ProcessChannelMode.SeparateChannels)
        process_env = QtCore.QProcessEnvironment.systemEnvironment()
        for key, value in prepared.env.items():
            process_env.insert(str(key), str(value))
        process.setProcessEnvironment(process_env)

        def read_stdout() -> None:
            data = bytes(process.readAllStandardOutput()).decode("utf-8", errors="replace")
            state["stdout"].append(data)
            append_output(data)
            status.setText(f"Статус: running; stdout {len(''.join(state['stdout'])) // 1024} KiB")
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
        output.setPlainText(prepared.start_text())
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
            start_prepared_process(prepare_blockcheck_execution(root=root, options=collect_options()))
        except BlockcheckPreparationError as exc:
            output.setPlainText(exc.result.to_text())
        except Exception as exc:  # pragma: no cover - GUI diagnostic path
            output.setPlainText(f"Blockcheck run: ошибка подготовки\n{exc}")

    def stop_blockcheck() -> None:
        process = state.get("process")
        if process is None:
            return
        state["stopped_by_user"] = True
        append_output("\n[GUI] Stop requested by owner; sending terminate() to blockcheck process…")
        status.setText("Статус: stop requested…")
        process.terminate()
        QtCore.QTimer.singleShot(3000, lambda: process.kill() if state.get("process") is process else None)

    preflight_button.clicked.connect(lambda _checked=False: run_action("Preflight", lambda: blockcheck_preflight_to_text(root=root)))
    build_plan_button.clicked.connect(lambda _checked=False: run_action("План binaries", lambda: blockcheck_build_plan_to_text(root=root)))
    build_button.clicked.connect(lambda _checked=False: build_binaries())
    plan_button.clicked.connect(lambda _checked=False: run_action("План run", lambda: blockcheck_plan_to_text(root=root, options=collect_options())))
    run_button.clicked.connect(lambda _checked=False: run_blockcheck())
    stop_button.clicked.connect(lambda _checked=False: stop_blockcheck())
    export_button.clicked.connect(lambda _checked=False: run_action("Создать стратегии", lambda: export_blockcheck_available_strategies(root=root).to_text()))
    log_button.clicked.connect(lambda _checked=False: run_action("Последний лог", lambda: last_blockcheck_log_to_text(root=root)))

    layout.addWidget(title)
    layout.addWidget(intro)
    layout.addWidget(form_box)
    layout.addLayout(buttons)
    layout.addWidget(status)
    layout.addWidget(output, 1)
    return page
