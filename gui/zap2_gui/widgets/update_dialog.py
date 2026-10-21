"""Окно «Обновление»: проверить репозиторий и пересобрать/установить пакет по шагам."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable, Optional

from ..adapters.self_update import UPDATE_STEPS, UpdateStatus, check_update, is_checkout, run_update
from ..qt_compat import require_pyqt

SETTINGS_CHECKOUT = "update/checkout"
SETTINGS_AUTO_CHECK = "update/auto-check"
SETTINGS_LAST_CHECK = "update/last-check"
AUTO_CHECK_INTERVAL_S = 20 * 3600


def guess_checkout(settings: Any, project_root: Path | None = None) -> Path | None:
    """Каталог checkout: из настроек, из текущего запуска или из типичных мест — без сети."""

    saved = str(settings.value(SETTINGS_CHECKOUT, "") or "")
    candidates = [Path(saved)] if saved else []
    if project_root is not None:
        candidates.append(project_root)
    home = Path.home()
    candidates += [home / "z2guiflin", *sorted(home.glob("projects/z2guiflin")), *sorted(home.glob("projects/*/z2guiflin"))]
    return next((path for path in candidates if is_checkout(path)), None)


def auto_check_due(settings: Any, now: float | None = None) -> bool:
    enabled = str(settings.value(SETTINGS_AUTO_CHECK, "true")).lower() not in {"false", "0", "no"}
    if not enabled:
        return False
    try:
        last = float(settings.value(SETTINGS_LAST_CHECK, 0) or 0)
    except (TypeError, ValueError):
        last = 0.0
    return (now or time.time()) - last >= AUTO_CHECK_INTERVAL_S


def make_update_worker(QtCore: Any, job: Callable[[Callable[[str], None]], Any]) -> Any:
    class _Worker(QtCore.QThread):  # type: ignore[misc, valid-type]
        line = QtCore.pyqtSignal(str)
        done = QtCore.pyqtSignal(object)

        def run(self) -> None:  # pragma: no cover - фоновый поток
            try:
                result = job(self.line.emit)
            except Exception as exc:  # noqa: BLE001 - показать пользователю, а не уронить GUI
                self.line.emit(f"✗ {exc}")
                result = None
            self.done.emit(result)

    return _Worker()


def make_update_dialog(parent: Any, settings: Any, project_root: Path | None, stop_runtime: Callable[[], str],
                       on_status: Optional[Callable[[UpdateStatus], None]] = None) -> Any:
    QtCore, QtWidgets = require_pyqt()
    dialog = QtWidgets.QDialog(parent)
    dialog.setObjectName("updateDialog")
    dialog.setWindowTitle("Обновление z2guiflin")
    dialog.resize(720, 520)
    layout = QtWidgets.QVBoxLayout(dialog)

    intro = QtWidgets.QLabel(
        "Программа сравнивает установленный пакет с checkout репозитория и новыми коммитами на GitHub. "
        "«Обновить» сначала останавливает запущенное, затем собирает и ставит пакет. Пароль спросит система."
    )
    intro.setWordWrap(True)
    layout.addWidget(intro)

    path_row = QtWidgets.QHBoxLayout()
    path_edit = QtWidgets.QLineEdit()
    path_edit.setObjectName("updateCheckoutPath")
    path_edit.setPlaceholderText("каталог checkout z2guiflin")
    found = guess_checkout(settings, project_root)
    path_edit.setText(str(found) if found else "")
    browse = QtWidgets.QPushButton("Выбрать…")
    path_row.addWidget(QtWidgets.QLabel("Checkout:"))
    path_row.addWidget(path_edit, 1)
    path_row.addWidget(browse)
    layout.addLayout(path_row)

    auto = QtWidgets.QCheckBox("Проверять обновления при запуске (не чаще раза в сутки; только git fetch)")
    auto.setObjectName("updateAutoCheck")
    auto.setChecked(str(settings.value(SETTINGS_AUTO_CHECK, "true")).lower() not in {"false", "0", "no"})
    layout.addWidget(auto)

    steps = QtWidgets.QLabel("Шаги обновления: " + " → ".join(step.title.split(" (")[0] for step in UPDATE_STEPS))
    steps.setWordWrap(True)
    steps.setObjectName("mutedText")
    layout.addWidget(steps)

    output = QtWidgets.QPlainTextEdit()
    output.setObjectName("updateOutput")
    output.setReadOnly(True)
    layout.addWidget(output, 1)

    buttons = QtWidgets.QHBoxLayout()
    check_button = QtWidgets.QPushButton("Проверить")
    check_button.setObjectName("updateCheckButton")
    update_button = QtWidgets.QPushButton("Обновить")
    update_button.setObjectName("updateRunButton")
    update_button.setEnabled(False)
    close_button = QtWidgets.QPushButton("Закрыть")
    buttons.addWidget(check_button)
    buttons.addWidget(update_button)
    buttons.addStretch(1)
    buttons.addWidget(close_button)
    layout.addLayout(buttons)

    holder: dict[str, Any] = {}

    def checkout() -> Path | None:
        text = path_edit.text().strip()
        return Path(text).expanduser() if text else None

    def remember() -> None:
        if checkout() is not None:
            settings.setValue(SETTINGS_CHECKOUT, str(checkout()))
        settings.setValue(SETTINGS_AUTO_CHECK, "true" if auto.isChecked() else "false")

    def busy(value: bool) -> None:
        check_button.setEnabled(not value)
        update_button.setEnabled(False if value else holder.get("available", False))
        path_edit.setEnabled(not value)

    def start(job: Callable[[Callable[[str], None]], Any], finished: Callable[[Any], None]) -> None:
        if holder.get("worker") is not None:
            return
        busy(True)
        worker = make_update_worker(QtCore, job)
        worker.line.connect(output.appendPlainText)

        def on_done(result: Any) -> None:
            holder.pop("worker", None)
            finished(result)
            busy(False)

        worker.done.connect(on_done)
        holder["worker"] = worker
        worker.start()

    def run_check() -> None:
        remember()
        output.setPlainText("Проверка…")
        target = checkout()

        def job(_log: Callable[[str], None]) -> UpdateStatus:
            return check_update(target)

        def finished(status: Any) -> None:
            if isinstance(status, UpdateStatus):
                settings.setValue(SETTINGS_LAST_CHECK, time.time())
                output.setPlainText(status.to_text())
                holder["available"] = status.available
                if on_status is not None:
                    on_status(status)

        start(job, finished)

    def run_full_update() -> None:
        target = checkout()
        if target is None:
            return
        answer = QtWidgets.QMessageBox.question(
            dialog, "Обновить z2guiflin",
            "Будет остановлено всё запущенное (zapret, туннель), затем собран и установлен пакет. Продолжить?",
        )
        if answer != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        remember()
        output.clear()

        def job(log: Callable[[str], None]) -> bool:
            return run_update(target, log=log, stop_runtime=stop_runtime)

        def finished(ok: Any) -> None:
            holder["available"] = not ok

        start(job, finished)

    def browse_checkout() -> None:
        chosen = QtWidgets.QFileDialog.getExistingDirectory(dialog, "Каталог checkout z2guiflin", path_edit.text())
        if chosen:
            path_edit.setText(chosen)

    check_button.clicked.connect(lambda _checked=False: run_check())
    update_button.clicked.connect(lambda _checked=False: run_full_update())
    browse.clicked.connect(lambda _checked=False: browse_checkout())
    close_button.clicked.connect(dialog.accept)
    auto.toggled.connect(lambda _value: remember())
    dialog.run_check = run_check
    return dialog


__all__ = ["auto_check_due", "guess_checkout", "make_update_dialog", "make_update_worker"]
