"""PyQt blockcheck lab page for manual strategy discovery."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from ..adapters.blockcheck_gui import (
    BLOCKCHECK_DEAD_TARGET_GUARD_AUTO_STOP,
    BLOCKCHECK_DEAD_TARGET_GUARD_OBSERVE_ONLY,
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
    request_blockcheck_graceful_stop,
    write_blockcheck_last_log,
)
from ..adapters.discord_verification import discord_non_voice_verification_plan_to_text
from ..adapters.discord_endpoint_discovery import (
    discord_endpoint_discovery_plan_to_text,
    discord_endpoint_report_to_text,
    discord_netlog_plan_to_text,
)
from ..adapters.har_workbench import (
    build_har_workbench,
    get_har_workbench_group,
    har_group_plan_to_text,
    har_workbench_report_to_text,
    latest_har_workbench,
)
from ..adapters.discord_voice_profiles import discord_voice_profiles_to_text
from ..models.service_targets import (
    DEFAULT_BLOCKCHECK_TARGET_STRING,
    SERVICE_COVERAGE_ORDERED_TARGET_CHAIN,
    SERVICE_TARGET_CUSTOM,
    SERVICE_TARGET_DISCORD_DESKTOP,
    get_service_target_preset,
    service_target_phase_chain,
    service_target_policy,
    service_target_recommended_scan_mode,
    list_service_target_presets,
)
from ..qt_compat import require_pyqt


BLOCKCHECK_LAB_CONTENT_WIDTH = 1160
BLOCKCHECK_LAB_SECTION_MIN_WIDTH = 560
BLOCKCHECK_LAB_SIDE_MIN_WIDTH = 360
BLOCKCHECK_LAB_OUTPUT_MIN_HEIGHT = 300


def make_blockcheck_lab_page(root: Path | None = None) -> Any:
    """Create a GUI page that wraps upstream blockcheck2.sh explicitly."""

    QtCore, QtWidgets = require_pyqt()
    page = QtWidgets.QWidget()
    page_layout = QtWidgets.QVBoxLayout(page)
    page_layout.setContentsMargins(0, 0, 0, 0)
    page_layout.setSpacing(0)

    scroll = QtWidgets.QScrollArea()
    scroll.setObjectName("blockcheckLabScrollArea")
    scroll.setWidgetResizable(True)
    scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    try:
        scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
    except Exception:  # pragma: no cover - PyQt compatibility
        pass
    page_layout.addWidget(scroll)

    content = QtWidgets.QWidget()
    content.setObjectName("blockcheckLabContent")
    scroll.setWidget(content)
    layout = QtWidgets.QVBoxLayout(content)
    layout.setContentsMargins(14, 10, 14, 14)
    layout.setSpacing(10)
    try:
        content.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Preferred,
        )
    except Exception:  # pragma: no cover - PyQt compatibility
        pass

    title = QtWidgets.QLabel("Диагностика: Blockcheck lab")
    title.setObjectName("pageTitle")
    intro = QtWidgets.QLabel(
        "Blockcheck lab: прогон upstream blockcheck2.sh по service target preset, экспорт найденных AVAILABLE стратегий "
        "и coverage/tournament диагностика. Запуск требует sudo и временно меняет firewall redirect внутри blockcheck; "
        "перед запуском выключите Default workflow/VPN. Долгий run идёт в фоне, остановка — отдельной кнопкой."
    )
    intro.setWordWrap(True)
    intro.setObjectName("blockcheckIntro")

    form_box = QtWidgets.QGroupBox("Параметры scan")
    form_box.setObjectName("blockcheckScanBox")
    form = QtWidgets.QGridLayout(form_box)
    form.setContentsMargins(10, 14, 10, 10)
    form.setHorizontalSpacing(6)
    form.setVerticalSpacing(3)

    target_preset_combo = QtWidgets.QComboBox()
    target_preset_combo.setObjectName("blockcheckServiceTargetPreset")
    target_preset_combo.setMinimumHeight(32)
    target_preset_combo.setMinimumWidth(260)
    target_preset_combo.setMaximumWidth(860)
    target_preset_combo.setMinimumContentsLength(24)
    try:
        target_preset_combo.setSizeAdjustPolicy(QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
    except Exception:  # pragma: no cover - PyQt compatibility
        pass
    for preset in list_service_target_presets():
        target_preset_combo.addItem(preset.title, preset.preset_id)

    target_preset_hint = QtWidgets.QLabel("")
    target_preset_hint.setObjectName("blockcheckPresetHint")
    target_preset_hint.setWordWrap(True)
    target_preset_hint.setMinimumHeight(30)
    target_preset_hint.setMaximumHeight(50)
    target_preset_hint.setMaximumWidth(900)
    target_preset_hint.setContentsMargins(2, 0, 0, 0)

    domains_edit = QtWidgets.QLineEdit(DEFAULT_BLOCKCHECK_TARGET_STRING)
    domains_edit.setObjectName("blockcheckDomainsEdit")
    domains_edit.setPlaceholderText(DEFAULT_BLOCKCHECK_TARGET_STRING)
    domains_edit.setMinimumHeight(32)
    domains_edit.setMinimumWidth(260)
    domains_edit.setMaximumWidth(860)
    domains_edit.setToolTip("Registry-owned presets keep this field read-only; Custom manual targets makes it editable.")

    scan_mode_combo = QtWidgets.QComboBox()
    scan_mode_combo.setObjectName("blockcheckCandidateScanMode")
    scan_mode_combo.setMinimumHeight(32)
    scan_mode_combo.setMinimumWidth(260)
    scan_mode_combo.setMaximumWidth(860)
    scan_mode_combo.addItem("Stop after first AVAILABLE", BLOCKCHECK_SCAN_STOP_AFTER_FIRST_AVAILABLE)
    scan_mode_combo.addItem("Scan all preset targets", BLOCKCHECK_SCAN_ALL_TARGETS)
    scan_mode_combo.addItem("Skip only dead targets", BLOCKCHECK_SCAN_SKIP_DEAD_ONLY)

    test_combo = QtWidgets.QComboBox()
    test_combo.addItems(["standard", "custom"])

    scan_combo = QtWidgets.QComboBox()
    scan_combo.addItems(["quick", "standard", "force"])

    ip_combo = QtWidgets.QComboBox()
    ip_combo.addItems(["4", "6", "46"])

    for compact_combo in (test_combo, scan_combo, ip_combo):
        compact_combo.setMinimumHeight(28)
        compact_combo.setMinimumWidth(140)
        compact_combo.setMaximumWidth(220)

    repeats_spin = QtWidgets.QSpinBox()
    repeats_spin.setRange(1, 5)
    repeats_spin.setValue(1)

    phase_budget_spin = QtWidgets.QSpinBox()
    phase_budget_spin.setRange(0, 999)
    phase_budget_spin.setValue(0)
    phase_budget_spin.setSpecialValueText("off")
    phase_budget_spin.setToolTip("For ordered phase runs: stop a phase alternative after this many strategy checks if no AVAILABLE appeared yet. 0 = no check budget.")

    timeout_spin = QtWidgets.QSpinBox()
    timeout_spin.setRange(1, 15)
    timeout_spin.setValue(3)
    timeout_spin.setSuffix(" сек")
    for compact_spin in (repeats_spin, timeout_spin, phase_budget_spin):
        compact_spin.setMinimumHeight(28)
        compact_spin.setMinimumWidth(112)

    http_check = QtWidgets.QCheckBox("HTTP")
    https12_check = QtWidgets.QCheckBox("HTTPS TLS1.2")
    https13_check = QtWidgets.QCheckBox("HTTPS TLS1.3")
    http3_check = QtWidgets.QCheckBox("HTTP/3 QUIC")
    dns_check = QtWidgets.QCheckBox("DNS precheck")
    dead_guard_check = QtWidgets.QCheckBox("Auto-skip dead target")
    dead_guard_check.setToolTip("For simple targets this can skip obvious dead TCP/443 candidates. For Discord ordered phases it is disabled by default because CDN/updater port precheck can be a false negative.")
    http_check.setChecked(False)
    https12_check.setChecked(True)
    https13_check.setChecked(True)
    http3_check.setChecked(True)
    dns_check.setChecked(False)
    dead_guard_check.setChecked(True)

    def form_label(text: str) -> Any:
        label = QtWidgets.QLabel(text)
        try:
            label.setAlignment(
                QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter
            )
        except Exception:  # pragma: no cover - PyQt compatibility
            pass
        return label

    form.addWidget(form_label("Service target"), 0, 0)
    form.addWidget(target_preset_combo, 0, 1, 1, 3)
    form.addWidget(target_preset_hint, 1, 0, 1, 4)
    form.addWidget(form_label("Домены/URI"), 2, 0)
    form.addWidget(domains_edit, 2, 1, 1, 3)
    form.addWidget(form_label("Candidate mode"), 3, 0)
    form.addWidget(scan_mode_combo, 3, 1, 1, 3)
    form.addWidget(form_label("Набор"), 4, 0)
    form.addWidget(test_combo, 4, 1)
    form.addWidget(form_label("Scanlevel"), 4, 2)
    form.addWidget(scan_combo, 4, 3)
    form.addWidget(form_label("IP"), 5, 0)
    form.addWidget(ip_combo, 5, 1)
    form.addWidget(form_label("Repeats"), 5, 2)
    form.addWidget(repeats_spin, 5, 3)
    form.addWidget(form_label("Curl timeout"), 6, 0)
    form.addWidget(timeout_spin, 6, 1)
    form.addWidget(form_label("Alt check cap"), 6, 2)
    form.addWidget(phase_budget_spin, 6, 3)
    form.addWidget(http_check, 7, 0)
    form.addWidget(https12_check, 7, 1)
    form.addWidget(https13_check, 7, 2)
    form.addWidget(http3_check, 7, 3)
    form.addWidget(dns_check, 8, 0, 1, 2)
    form.addWidget(dead_guard_check, 8, 2, 1, 2)
    form.setColumnMinimumWidth(0, 72)
    form.setColumnMinimumWidth(1, 128)
    form.setColumnMinimumWidth(2, 76)
    form.setColumnMinimumWidth(3, 128)
    form.setColumnStretch(0, 0)
    form.setColumnStretch(1, 2)
    form.setColumnStretch(2, 0)
    form.setColumnStretch(3, 2)
    form_box.setMinimumHeight(0)
    form_box.setMinimumWidth(BLOCKCHECK_LAB_SECTION_MIN_WIDTH)
    form_box.setMaximumWidth(650)
    form_box.setMaximumHeight(390)
    try:
        form_box.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Preferred,
            QtWidgets.QSizePolicy.Policy.Maximum,
        )
    except Exception:  # pragma: no cover - PyQt compatibility
        pass

    actions_box = QtWidgets.QGroupBox("Actions")
    actions_box.setMinimumWidth(BLOCKCHECK_LAB_SIDE_MIN_WIDTH)
    actions_layout = QtWidgets.QGridLayout(actions_box)
    actions_layout.setContentsMargins(10, 10, 10, 10)
    actions_layout.setHorizontalSpacing(6)
    actions_layout.setVerticalSpacing(6)
    preflight_button = QtWidgets.QPushButton("Preflight")
    build_plan_button = QtWidgets.QPushButton("Binaries plan")
    build_button = QtWidgets.QPushButton("Build binaries")
    plan_button = QtWidgets.QPushButton("Run plan")
    run_button = QtWidgets.QPushButton("▶")
    stop_button = QtWidgets.QPushButton("■")
    run_button.setObjectName("blockcheckPrimaryRunButton")
    stop_button.setObjectName("blockcheckStopButton")
    run_button.setToolTip("Запустить Blockcheck run")
    stop_button.setToolTip("Остановить текущий Blockcheck run")
    export_button = QtWidgets.QPushButton("Export strategies")
    coverage_button = QtWidgets.QPushButton("Coverage")
    policy_button = QtWidgets.QPushButton("Policy")
    tournament_button = QtWidgets.QPushButton("Tournament")
    verify_button = QtWidgets.QPushButton("Checklist")
    endpoint_button = QtWidgets.QPushButton("Endpoints")
    log_button = QtWidgets.QPushButton("Raw log")
    har_import_button = QtWidgets.QPushButton("HAR import")
    har_report_button = QtWidgets.QPushButton("HAR report")
    har_load_button = QtWidgets.QPushButton("Load HAR group")
    voice_profiles_button = QtWidgets.QPushButton("Voice profiles")
    har_group_combo = QtWidgets.QComboBox()
    har_group_combo.setObjectName("blockcheckHarGroupCombo")
    har_group_combo.setToolTip("Группы любого ресурса из последнего sanitized HAR workbench")
    stop_button.setEnabled(False)
    for action_button in (
        preflight_button, build_plan_button, build_button, plan_button, run_button, stop_button,
        export_button, coverage_button, policy_button, tournament_button, verify_button, endpoint_button, log_button,
        har_import_button, har_report_button, har_load_button, voice_profiles_button,
    ):
        action_button.setMinimumHeight(30)
        action_button.setMinimumWidth(76)
        action_button.setMaximumWidth(220)
        try:
            action_button.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Expanding,
                QtWidgets.QSizePolicy.Policy.Fixed,
            )
        except Exception:  # pragma: no cover - PyQt compatibility
            pass
    run_button.setFixedWidth(40)
    stop_button.setFixedWidth(40)
    export_button.setMinimumWidth(118)
    action_grid = (
        (preflight_button, 0, 0, 1, 1),
        (plan_button, 0, 1, 1, 1),
        (run_button, 0, 2, 1, 1),
        (stop_button, 0, 3, 1, 1),
        (export_button, 1, 0, 1, 2),
        (coverage_button, 1, 2, 1, 2),
        (build_plan_button, 2, 0, 1, 2),
        (build_button, 2, 2, 1, 2),
        (policy_button, 3, 0, 1, 2),
        (tournament_button, 3, 2, 1, 2),
        (verify_button, 4, 0, 1, 2),
        (endpoint_button, 4, 2, 1, 2),
        (log_button, 5, 0, 1, 4),
        (har_import_button, 6, 0, 1, 2),
        (har_report_button, 6, 2, 1, 2),
        (har_group_combo, 7, 0, 1, 4),
        (har_load_button, 8, 0, 1, 2),
        (voice_profiles_button, 8, 2, 1, 2),
    )
    for button, row, column, row_span, column_span in action_grid:
        actions_layout.addWidget(button, row, column, row_span, column_span)
    for column in range(4):
        actions_layout.setColumnStretch(column, 1)

    status = QtWidgets.QLabel("Статус: idle")
    status.setObjectName("blockcheckStatusPill")
    status.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

    output = QtWidgets.QPlainTextEdit()
    output.setObjectName("blockcheckOutput")
    output.setReadOnly(True)
    output.setMinimumHeight(BLOCKCHECK_LAB_OUTPUT_MIN_HEIGHT)
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
        "gui_log_mode": False,
        "tournament_best": None,
        "tournament_records": [],
        "candidate_targets": [],
        "candidate_index": 0,
        "phase_gated_run": False,
        "candidate_phase_groups": [],
        "candidate_phase_index": 0,
        "candidate_phase_had_available": False,
        "candidate_budget_stop": False,
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
            if preset.preset_id == SERVICE_TARGET_DISCORD_DESKTOP:
                dead_guard_check.setChecked(False)
                phase_budget_spin.setValue(160)
            elif preset.preset_id != SERVICE_TARGET_CUSTOM:
                dead_guard_check.setChecked(True)
                phase_budget_spin.setValue(0)
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
            dead_target_guard=(
                BLOCKCHECK_DEAD_TARGET_GUARD_AUTO_STOP
                if dead_guard_check.isChecked()
                else BLOCKCHECK_DEAD_TARGET_GUARD_OBSERVE_ONLY
            ),
        )

    def append_output(text: str) -> None:
        if not text:
            return
        output.appendPlainText(text.rstrip("\n"))
        scrollbar = output.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def phase_group_title(phase_index: int) -> str:
        try:
            phases = list(service_target_phase_chain(selected_target_preset_id()))
        except Exception:
            phases = []
        if 0 <= phase_index < len(phases):
            phase = phases[phase_index]
            return f"{phase.phase_id} ({phase.title})"
        return f"phase {phase_index + 1}"

    def strategy_label(stats: Any) -> str:
        strategies = tuple(getattr(stats, "available_strategies", ()) or ())
        if not strategies:
            return "<пока нет AVAILABLE strategy>"
        first = strategies[0]
        return first if len(first) <= 180 else first[:177] + "..."

    def remember_tournament_record(target: str, phase_index: int, stats: Any) -> None:
        record = {
            "target": target,
            "phase_index": phase_index,
            "phase_title": phase_group_title(phase_index),
            "available": int(getattr(stats, "available", 0) or 0),
            "checks": int(getattr(stats, "strategy_attempts", 0) or 0),
            "strategy": strategy_label(stats),
        }
        state["tournament_best"] = record
        records = list(state.get("tournament_records") or [])
        records.append(record)
        state["tournament_records"] = records[-5:]

    def tournament_record_text() -> str:
        best = state.get("tournament_best")
        if not isinstance(best, dict):
            return "рекордсмен: пока нет"
        return (
            "рекордсмен: "
            f"phase {int(best.get('phase_index', 0)) + 1} {best.get('phase_title')} / {best.get('target')} "
            f"(available={best.get('available', 0)}, checks={best.get('checks', 0)})"
        )

    def tournament_top_text() -> str:
        records = [item for item in (state.get("tournament_records") or []) if isinstance(item, dict)]
        if not records:
            return "топ стратегий: пока пусто"
        lines = ["топ стратегий:"]
        for index, record in enumerate(records[-3:], 1):
            lines.append(
                "  - "
                f"#{index}: phase {int(record.get('phase_index', 0)) + 1} {record.get('phase_title')} / {record.get('target')} "
                f"available={record.get('available', 0)}; strategy={record.get('strategy')}"
            )
        return "\n".join(lines)

    def phase_alt_budget() -> int:
        try:
            return int(phase_budget_spin.value())
        except Exception:
            return 0

    def should_budget_stop_phase_alternative(stats: Any) -> bool:
        if not state.get("phase_gated_run"):
            return False
        if getattr(stats, "available", 0) > 0:
            return False
        budget = phase_alt_budget()
        if budget <= 0:
            return False
        return int(getattr(stats, "strategy_attempts", 0) or 0) >= budget

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
        dead_guard_check.setEnabled(not running)
        phase_budget_spin.setEnabled(not running)
        for button in (
            preflight_button, build_plan_button, build_button, plan_button, run_button, export_button, coverage_button,
            policy_button, tournament_button, verify_button, endpoint_button, log_button, har_import_button,
            har_report_button, har_load_button, voice_profiles_button,
        ):
            button.setEnabled(not running)
        har_group_combo.setEnabled(not running)
        har_load_button.setEnabled(not running and bool(har_group_combo.currentData()))
        stop_button.setEnabled(running)
        if running:
            targets = state.get("candidate_targets") or []
            index = int(state.get("candidate_index") or 0)
            if targets:
                phase_groups = state.get("candidate_phase_groups") or []
                if state.get("phase_gated_run") and phase_groups:
                    phase_index = int(state.get("candidate_phase_index") or 0)
                    status.setText(
                        f"Статус: tournament phase {phase_index + 1}/{len(phase_groups)}, "
                        f"candidate {index + 1}/{len(targets)} выполняется…"
                    )
                else:
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

    def refresh_har_groups() -> None:
        har_group_combo.clear()
        workbench = latest_har_workbench(root=root)
        if workbench is None:
            har_group_combo.addItem("HAR workbench отсутствует", "")
            har_load_button.setEnabled(False)
            return
        groups = workbench.blockcheck_groups()
        if not groups:
            har_group_combo.addItem("Нет domain-групп для Blockcheck", "")
            har_load_button.setEnabled(False)
            return
        for group in groups:
            issue_marker = "issues" if group.issue_hosts else "observed"
            har_group_combo.addItem(
                f"{group.domain_family} · {group.reason} · {group.protocol}/{group.l7} · {len(group.hosts)} hosts · {issue_marker}",
                group.group_id,
            )
        har_load_button.setEnabled(True)

    def import_har_workbench() -> None:
        if state.get("process") is not None:
            output.setPlainText("Blockcheck уже выполняется. Сначала остановите текущий run или дождитесь завершения.")
            return
        path, _selected_filter = QtWidgets.QFileDialog.getOpenFileName(
            page,
            "Импорт HAR для универсального workbench",
            str(root or Path.home()),
            "HAR files (*.har *.zip);;All files (*)",
        )
        if not path:
            return
        try:
            workbench = build_har_workbench(path, root=root)
            refresh_har_groups()
            output.setPlainText(workbench.to_text())
            status.setText("Статус: HAR workbench создан; выберите группу")
        except Exception as exc:  # pragma: no cover - GUI diagnostic path
            output.setPlainText(f"HAR workbench: ошибка\n{exc}")

    def load_selected_har_group() -> None:
        group_id = str(har_group_combo.currentData() or "")
        if not group_id:
            output.setPlainText("HAR group не выбрана. Сначала импортируйте HAR или создайте workbench через CLI.")
            return
        try:
            group = get_har_workbench_group(group_id, root=root)
            custom_index = target_preset_combo.findData(SERVICE_TARGET_CUSTOM)
            if custom_index >= 0:
                target_preset_combo.setCurrentIndex(custom_index)
            apply_target_preset(SERVICE_TARGET_CUSTOM)
            domains_edit.setText(" ".join(group.hosts))
            state["custom_targets"] = domains_edit.text().strip()
            scan_index = scan_mode_combo.findData(BLOCKCHECK_SCAN_ALL_TARGETS)
            if scan_index >= 0:
                scan_mode_combo.setCurrentIndex(scan_index)
            http_check.setChecked(group.l7 == "http")
            https12_check.setChecked(group.l7 in {"tls", "websocket"})
            https13_check.setChecked(group.l7 in {"tls", "websocket"})
            http3_check.setChecked(group.l7 == "quic")
            dead_guard_check.setChecked(False)
            phase_budget_spin.setValue(0)
            output.setPlainText(har_group_plan_to_text(group_id, root=root))
            status.setText(f"Статус: HAR group loaded · {group_id}")
        except Exception as exc:  # pragma: no cover - GUI diagnostic path
            output.setPlainText(f"Load HAR group: ошибка\n{exc}")

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
            state["phase_gated_run"] = False
            state["tournament_best"] = None
            state["tournament_records"] = []
            state["candidate_phase_groups"] = []
            state["candidate_phase_index"] = 0
            state["candidate_phase_had_available"] = False
            state["candidate_budget_stop"] = False
            set_running(False)
            return

        target = str(targets[index])
        state["candidate_budget_stop"] = False
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

        if state.get("phase_gated_run"):
            phase_groups = list(state.get("candidate_phase_groups") or [])
            phase_index = int(state.get("candidate_phase_index") or 0)
            phase_targets = list(phase_groups[phase_index]) if phase_index < len(phase_groups) else targets
            phase_label = phase_group_title(phase_index)
            append_output(
                "\n[GUI tournament] "
                f"Фаза {phase_index + 1}/{len(phase_groups)} {phase_label}: "
                f"проверяем alternative {index + 1}/{len(phase_targets)} — {target}"
            )
            append_output(
                "[GUI tournament] Сырой upstream log пишется в файл; в этом окне показывается человекочитаемый прогресс."
            )
        else:
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
        target = ""
        if prepared is not None:
            try:
                target = prepared.command.options.normalized_domains()[0]
            except Exception:
                target = ""
        footer = [
            "",
            "===== FINISHED =====",
            f"return code: {exit_code}",
            f"exit status: {exit_status}",
            f"stopped by owner: {'yes' if stopped else 'no'}",
            f"auto stopped candidate: {'yes' if auto_skip_reason else 'no'}",
        ]
        if auto_skip_reason:
            footer.append(f"auto stop reason: {auto_skip_reason}")
        if prepared is not None:
            footer.append(f"log path: {prepared.command.log_path or 'не задан'}")
        if stats.has_observations:
            footer.extend(["", stats.to_text()])
        if summary:
            footer.extend(["", "Parsed SUMMARY / working strategy hints:"])
            footer.extend(f"- {line}" for line in summary)
        footer_text = "\n".join(footer)
        if state.get("phase_gated_run"):
            phase_index = int(state.get("candidate_phase_index") or 0)
            phase_label = phase_group_title(phase_index)
            budget_stopped = bool(state.get("candidate_budget_stop"))
            if stopped:
                append_output(
                    "\n[GUI tournament] Блокчек остановлен вручную; "
                    + tournament_record_text()
                    + "\n"
                    + tournament_top_text()
                )
            elif stats.available > 0:
                remember_tournament_record(target, phase_index, stats)
                append_output(
                    "\n[GUI tournament] Найдена AVAILABLE стратегия для фазы "
                    f"{phase_index + 1} {phase_label}: target={target}; available={stats.available}; checks={stats.strategy_attempts}"
                )
                append_output(f"[GUI tournament] стратегия-рекордсмен: {strategy_label(stats)}")
            elif budget_stopped:
                append_output(
                    "\n[GUI tournament] Alternative достигла лимита проверок без AVAILABLE "
                    f"для фазы {phase_index + 1} {phase_label}: target={target}; "
                    f"checks={stats.strategy_attempts}; cap={phase_alt_budget()}. "
                    + tournament_record_text()
                )
            else:
                append_output(
                    "\n[GUI tournament] Стратегия/alternative не прошла фазу "
                    f"{phase_index + 1} {phase_label}: target={target}; verdict={stats.verdict}; checks={stats.strategy_attempts}. "
                    + tournament_record_text()
                )
        else:
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

        if not stopped and state.get("phase_gated_run"):
            phase_groups = list(state.get("candidate_phase_groups") or [])
            phase_index = int(state.get("candidate_phase_index") or 0)
            phase_passed = bool(state.get("candidate_phase_had_available")) or stats.available > 0
            if phase_passed:
                next_phase_index = phase_index + 1
                if next_phase_index < len(phase_groups):
                    state["candidate_phase_index"] = next_phase_index
                    state["candidate_targets"] = list(phase_groups[next_phase_index])
                    state["candidate_index"] = 0
                    state["candidate_phase_had_available"] = False
                    append_output(
                        "\n[GUI tournament] Фаза пройдена; переходим к следующей обязательной фазе "
                        f"{next_phase_index + 1}/{len(phase_groups)}. " + tournament_record_text()
                    )
                    status.setText("Статус: переход к следующей tournament phase…")
                    QtCore.QTimer.singleShot(250, start_next_candidate)
                    return
                append_output(
                    "\n[GUI tournament] Блокчек завершил работу по прохождению всех фаз; "
                    + tournament_record_text()
                    + "\n"
                    + tournament_top_text()
                )
                state["candidate_targets"] = []
                state["candidate_index"] = 0
                state["phase_gated_run"] = False
                state["candidate_phase_groups"] = []
                state["candidate_phase_index"] = 0
                state["candidate_phase_had_available"] = False
                set_running(False)
                return

            if next_exists:
                state["candidate_index"] = current_index + 1
                append_output("\n[GUI tournament] Alternative не прошла текущую фазу; пробуем следующий target внутри этой же фазы.")
                status.setText("Статус: переход к alternative внутри текущей phase…")
                QtCore.QTimer.singleShot(250, start_next_candidate)
                return

            phase_label = f"{phase_index + 1}/{len(phase_groups)}" if phase_groups else str(phase_index + 1)
            append_output(
                "\n[GUI tournament] Tournament phase blocked: no AVAILABLE alternative in required phase; "
                "Блокчек завершил работу: обязательная фаза заблокирована "
                f"({phase_label}), более поздние фазы не проверяются. "
                + tournament_record_text()
                + "\n"
                + tournament_top_text()
            )
            state["candidate_targets"] = []
            state["candidate_index"] = 0
            state["phase_gated_run"] = False
            state["tournament_best"] = None
            state["tournament_records"] = []
            state["candidate_phase_groups"] = []
            state["candidate_phase_index"] = 0
            state["candidate_phase_had_available"] = False
            state["candidate_budget_stop"] = False
            set_running(False)
            return

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
        state["phase_gated_run"] = False
        state["candidate_phase_groups"] = []
        state["candidate_phase_index"] = 0
        state["candidate_phase_had_available"] = False
        set_running(False)

    def handle_process_error(error: Any) -> None:
        if state.get("stopped_by_user") or state.get("auto_skip_reason"):
            # Qt may report a signal-stopped process as CrashExit. For an
            # explicit owner Stop or an evidence-based early stop this is
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
        dead_guard_enabled = prepared.command.options.dead_target_guard == BLOCKCHECK_DEAD_TARGET_GUARD_AUTO_STOP
        monitor = BlockcheckPortPrecheckMonitor(target=target) if dead_guard_enabled else None

        def request_auto_skip(reason: str) -> None:
            if state.get("auto_skip_reason") or state.get("stopped_by_user"):
                return
            state["auto_skip_reason"] = reason
            if state.get("phase_gated_run") and reason.startswith("phase-alternative-available"):
                message = (
                    "\n[GUI tournament] Достаточно evidence для текущей phase alternative; "
                    "останавливаем upstream scan и переходим дальше по tournament loop.\n"
                )
            elif state.get("phase_gated_run") and reason.startswith("phase-alternative-check-cap"):
                message = (
                    "\n[GUI tournament] Лимит проверок для текущей alternative достигнут без AVAILABLE; "
                    "останавливаем upstream scan и пробуем следующую alternative/phase.\n"
                )
            else:
                message = (
                    "\n[GUI] Evidence-based early stop: "
                    f"{reason}. Moving to the next candidate if one exists.\n"
                )
            state["stderr"].append(message)
            append_output(message)
            status.setText("Статус: candidate auto-stop requested; ожидается cleanup…")
            request_process_stop(process)

        def read_stdout() -> None:
            data = bytes(process.readAllStandardOutput()).decode("utf-8", errors="replace")
            state["stdout"].append(data)
            if not state.get("phase_gated_run"):
                append_output(data)
            status.setText(f"Статус: running; raw stdout {len(''.join(state['stdout'])) // 1024} KiB")
            reason = monitor.feed_stdout(data) if monitor is not None else ""
            if reason:
                request_auto_skip(reason)
            elif state.get("phase_gated_run"):
                stats = parse_blockcheck_run_stats("".join(state["stdout"]), "".join(state["stderr"]))
                if stats.available > 0:
                    state["candidate_phase_had_available"] = True
                    request_auto_skip(
                        f"phase-alternative-available for {target}: available={stats.available}; "
                        "moving to next required phase"
                    )
                elif should_budget_stop_phase_alternative(stats):
                    state["candidate_budget_stop"] = True
                    request_auto_skip(
                        f"phase-alternative-check-cap for {target}: checks={stats.strategy_attempts}; "
                        f"cap={phase_alt_budget()}; moving to next alternative"
                    )
            flush_live_log()

        def read_stderr() -> None:
            data = bytes(process.readAllStandardError()).decode("utf-8", errors="replace")
            state["stderr"].append(data)
            if not state.get("phase_gated_run"):
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
        elif state.get("phase_gated_run"):
            append_output(
                "[GUI tournament] raw log: "
                f"{prepared.command.candidate_log_path or prepared.command.log_path or 'не задан'}"
            )
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
                "Targets будут проверяться последовательно. Auto-skip dead target можно включать для простых проверок; "
                "для Discord ordered phases он выключен по умолчанию, чтобы port precheck не дал ложный dead-target на CDN/updater. "
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
            options = collect_options()
            targets = list(options.ordered_domains_for_policy())
            policy = service_target_policy(options.service_target_preset_id)
        except Exception as exc:
            output.setPlainText(f"Blockcheck run: ошибка параметров\n{exc}")
            return

        phase_groups: list[list[str]] = []
        phase_gated = (
            policy.mode == SERVICE_COVERAGE_ORDERED_TARGET_CHAIN
            and str(scan_mode_combo.currentData()) == BLOCKCHECK_SCAN_ALL_TARGETS
            and options.service_target_preset_id != SERVICE_TARGET_CUSTOM
        )
        if phase_gated:
            try:
                phase_groups = [list(phase.targets) for phase in service_target_phase_chain(options.service_target_preset_id) if phase.required]
            except Exception as exc:
                output.setPlainText(f"Blockcheck run: ошибка tournament phase policy\n{exc}")
                return
            if not phase_groups:
                phase_gated = False

        if phase_gated:
            state["phase_gated_run"] = True
            state["tournament_best"] = None
            state["tournament_records"] = []
            state["candidate_phase_groups"] = phase_groups
            state["candidate_phase_index"] = 0
            state["candidate_phase_had_available"] = False
            state["candidate_targets"] = phase_groups[0]
            state["candidate_index"] = 0
            phase_lines = [
                f"  {index + 1}. {' OR '.join(group)}"
                for index, group in enumerate(phase_groups)
            ]
            output.setPlainText(
                "GUI tournament log (Phase-gated Blockcheck tournament run)\n"
                "semantics: phases are AND; alternatives inside one phase are OR\n"
                "runner rule: do not advance to later phases until the current phase has an AVAILABLE alternative\n"
                "runner rule: when a phase alternative becomes AVAILABLE, stop that candidate and advance to the next phase\n"
                "raw upstream blockcheck output is written to Last log / candidate log files, not streamed here during phase-gated runs\n"
                f"candidate mode: {scan_mode_combo.currentData()}\n"
                "phases:\n"
                + "\n".join(phase_lines)
                + f"\ndead-target guard: {options.dead_target_guard}; evidence-based, no wall-clock timeout"
                + f"\nphase alternative check cap: {phase_alt_budget() or 'off'}"
            )
        else:
            state["phase_gated_run"] = False
            state["tournament_best"] = None
            state["tournament_records"] = []
            state["candidate_phase_groups"] = []
            state["candidate_phase_index"] = 0
            state["candidate_phase_had_available"] = False
            state["candidate_targets"] = targets
            state["candidate_index"] = 0
            output.setPlainText(
                "Sequential Blockcheck run\n"
                f"candidates: {', '.join(targets)}\n"
                f"candidate mode: {scan_mode_combo.currentData()}\n"
                f"dead-target guard: {options.dead_target_guard}; evidence-based, no wall-clock timeout"
                f"\nphase alternative check cap: {phase_alt_budget() or 'off'}"
            )
        start_next_candidate()

    def force_stop_if_current(process: Any) -> None:
        if state.get("process") is not process:
            return
        append_output("\n[GUI] SIGINT cleanup не завершился за 10 секунд; отправляется аварийный terminate().")
        process.terminate()
        QtCore.QTimer.singleShot(3000, lambda: process.kill() if state.get("process") is process else None)

    def request_process_stop(process: Any) -> None:
        if request_blockcheck_graceful_stop(process):
            append_output("\n[GUI] Отправлен SIGINT: ожидается upstream cleanup.")
            QtCore.QTimer.singleShot(10000, lambda: force_stop_if_current(process))
        else:
            force_stop_if_current(process)

    def stop_blockcheck() -> None:
        process = state.get("process")
        if process is None:
            return
        state["stopped_by_user"] = True
        append_output("\n[GUI] Stop requested by owner; sending SIGINT for upstream cleanup…")
        status.setText("Статус: stop requested; ожидается cleanup…")
        request_process_stop(process)

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
    endpoint_button.clicked.connect(
        lambda _checked=False: run_action(
            "Discord endpoints",
            lambda: discord_endpoint_discovery_plan_to_text() + "\n\n" + discord_endpoint_report_to_text(root=root) + "\n\n" + discord_netlog_plan_to_text(),
        )
    )
    log_button.clicked.connect(lambda _checked=False: run_action("Последний лог", lambda: last_blockcheck_log_to_text(root=root)))
    har_import_button.clicked.connect(lambda _checked=False: import_har_workbench())
    har_report_button.clicked.connect(lambda _checked=False: run_action("HAR workbench", lambda: har_workbench_report_to_text(root=root)))
    har_load_button.clicked.connect(lambda _checked=False: load_selected_har_group())
    voice_profiles_button.clicked.connect(lambda _checked=False: run_action("Discord Voice profiles", lambda: discord_voice_profiles_to_text(root=root)))
    refresh_har_groups()

    output.setMinimumHeight(BLOCKCHECK_LAB_OUTPUT_MIN_HEIGHT)
    output.setMinimumWidth(BLOCKCHECK_LAB_SIDE_MIN_WIDTH)
    try:
        output.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )
    except Exception:  # pragma: no cover - PyQt compatibility
        pass

    body = QtWidgets.QWidget()
    body.setObjectName("blockcheckTwoPaneBody")
    body.setMinimumWidth(980)
    body.setMaximumWidth(BLOCKCHECK_LAB_CONTENT_WIDTH)
    try:
        body.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )
    except Exception:  # pragma: no cover - PyQt compatibility
        pass
    body_layout = QtWidgets.QHBoxLayout(body)
    body_layout.setContentsMargins(0, 0, 0, 0)
    body_layout.setSpacing(12)

    right_column = QtWidgets.QWidget()
    right_column.setObjectName("blockcheckRightColumn")
    right_column.setMinimumWidth(BLOCKCHECK_LAB_SIDE_MIN_WIDTH)
    try:
        right_column.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )
    except Exception:  # pragma: no cover - PyQt compatibility
        pass
    right_layout = QtWidgets.QVBoxLayout(right_column)
    right_layout.setContentsMargins(0, 0, 0, 0)
    right_layout.setSpacing(8)
    right_layout.addWidget(actions_box, 0)
    right_layout.addWidget(status, 0)
    right_layout.addWidget(output, 1)

    body_layout.addWidget(form_box, 3, QtCore.Qt.AlignmentFlag.AlignTop)
    body_layout.addWidget(right_column, 2)

    title.setMinimumWidth(0)
    intro.setMinimumWidth(0)
    intro.setMaximumWidth(BLOCKCHECK_LAB_CONTENT_WIDTH)
    status.setMinimumWidth(BLOCKCHECK_LAB_SIDE_MIN_WIDTH)
    layout.addWidget(title)
    layout.addWidget(intro)
    layout.addWidget(body, 1)

    page.setStyleSheet(
        """
        QLabel#pageTitle {
            font-size: 18px;
            font-weight: 700;
        }
        QLabel#blockcheckIntro {
            padding: 4px 2px 6px 2px;
            margin-bottom: 2px;
        }
        QGroupBox#blockcheckScanBox {
            padding-top: 8px;
            margin-bottom: 0;
        }
        QGroupBox {
            margin-top: 8px;
            padding-top: 10px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 8px;
            padding: 0 6px;
            font-weight: 700;
        }
        QPushButton#blockcheckPrimaryRunButton {
            font-size: 18px;
            font-weight: 700;
            padding: 0;
            border-radius: 9px;
        }
        QPushButton#blockcheckStopButton {
            padding: 0;
            border-radius: 9px;
        }
        QLabel#blockcheckStatusPill {
            font-weight: 700;
            padding: 6px 10px;
            border-radius: 12px;
            background: #eee8f1;
        }
        QLabel#mutedText, QLabel#blockcheckPresetHint {
            color: #756d7b;
            font-size: 12px;
        }
        QCheckBox {
            spacing: 4px;
        }
        QPlainTextEdit#blockcheckOutput {
            font-family: monospace;
        }
        """
    )
    return page
