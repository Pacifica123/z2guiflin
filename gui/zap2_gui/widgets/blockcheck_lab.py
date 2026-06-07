"""PyQt blockcheck lab page for manual strategy discovery."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from ..adapters.blockcheck_gui import (
    BlockcheckOptions,
    blockcheck_build_plan_to_text,
    blockcheck_plan_to_text,
    blockcheck_preflight_to_text,
    execute_blockcheck_prereq_build,
    execute_blockcheck_with_gui_sudo,
    last_blockcheck_log_to_text,
)
from ..qt_compat import require_pyqt


def make_blockcheck_lab_page(root: Path | None = None) -> Any:
    """Create a GUI page that wraps upstream blockcheck2.sh explicitly."""

    _QtCore, QtWidgets = require_pyqt()
    page = QtWidgets.QWidget()
    layout = QtWidgets.QVBoxLayout(page)
    layout.setContentsMargins(14, 14, 14, 14)
    layout.setSpacing(10)

    title = QtWidgets.QLabel("Диагностика: Blockcheck lab")
    title.setObjectName("pageTitle")
    intro = QtWidgets.QLabel(
        "Здесь можно вручную прогнать upstream blockcheck2.sh для домена YouTube или другого target, "
        "посмотреть найденные стратегии и потом осознанно перенести удачную строку в каталог стратегий. "
        "Запуск требует sudo, временно меняет firewall redirect внутри blockcheck и должен выполняться при выключенном Default workflow/VPN."
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
    log_button = QtWidgets.QPushButton("Последний лог")
    buttons.addWidget(preflight_button)
    buttons.addWidget(build_plan_button)
    buttons.addWidget(build_button)
    buttons.addWidget(plan_button)
    buttons.addWidget(run_button)
    buttons.addWidget(log_button)
    buttons.addStretch(1)

    output = QtWidgets.QPlainTextEdit()
    output.setReadOnly(True)
    output.setMinimumHeight(300)
    try:
        output.setLineWrapMode(QtWidgets.QPlainTextEdit.LineWrapMode.WidgetWidth)
    except Exception:  # pragma: no cover - compatibility with older Qt bindings
        pass
    output.setPlainText(blockcheck_preflight_to_text(root=root))

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
        )

    def run_action(label: str, func: Callable[[], str]) -> None:
        try:
            output.setPlainText(func())
        except Exception as exc:  # pragma: no cover - GUI diagnostic path
            output.setPlainText(f"{label}: ошибка\n{exc}")

    def build_binaries() -> None:
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

    def run_blockcheck() -> None:
        question = QtWidgets.QMessageBox.question(
            page,
            "Blockcheck lab",
            (
                "Запустить upstream blockcheck2.sh через графический sudo prompt?\n\n"
                "Рекомендуется сначала выключить Default workflow, VPN и другие DPI-bypass процессы. "
                "Blockcheck временно меняет firewall redirect и затем очищает его через свой cleanup. "
                "Пароль не сохраняется приложением."
            ),
        )
        if question != QtWidgets.QMessageBox.StandardButton.Yes:
            output.setPlainText("Blockcheck run: отменено пользователем")
            return
        run_action("Blockcheck run", lambda: execute_blockcheck_with_gui_sudo(root=root, options=collect_options()).to_text())

    preflight_button.clicked.connect(lambda _checked=False: run_action("Preflight", lambda: blockcheck_preflight_to_text(root=root)))
    build_plan_button.clicked.connect(lambda _checked=False: run_action("План binaries", lambda: blockcheck_build_plan_to_text(root=root)))
    build_button.clicked.connect(lambda _checked=False: build_binaries())
    plan_button.clicked.connect(lambda _checked=False: run_action("План run", lambda: blockcheck_plan_to_text(root=root, options=collect_options())))
    run_button.clicked.connect(lambda _checked=False: run_blockcheck())
    log_button.clicked.connect(lambda _checked=False: run_action("Последний лог", lambda: last_blockcheck_log_to_text(root=root)))

    layout.addWidget(title)
    layout.addWidget(intro)
    layout.addWidget(form_box)
    layout.addLayout(buttons)
    layout.addWidget(output, 1)
    return page
