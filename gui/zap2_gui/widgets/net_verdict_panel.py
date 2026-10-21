"""Кнопка «Диагностика сети (вердикт)» для Blockcheck lab.

Самодостаточный модуль: замер идёт в QThread, UI не блокируется. Без sudo и
без изменений firewall; результат — текст вердикта и JSON в `.zap2/runtime/reports`.
После вердикта под кнопкой появляются переходы «Что попробовать» к нужным страницам.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Optional

from ..adapters.net_verdict import run_and_report
from ..models.remedy import remedies_for_verdict, remedy_hint

NET_VERDICT_BUTTON_TEXT = "Диагностика сети (вердикт)"
NET_VERDICT_BUTTON_OBJECT_NAME = "blockcheckNetVerdictButton"
NET_VERDICT_REMEDIES_OBJECT_NAME = "netVerdictRemedies"


def verdict_code_from_report(path: Any) -> str:
    """Код вердикта из JSON-отчёта; пустая строка, если отчёт не читается."""

    import json

    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return ""
    verdict = data.get("verdict") if isinstance(data, dict) else None
    return str(verdict.get("code", "")) if isinstance(verdict, dict) else ""


def make_net_verdict_button(
    QtCore: Any,
    QtWidgets: Any,
    output: Any,
    status: Any,
    root: Optional[Path] = None,
    is_busy: Optional[Callable[[], bool]] = None,
    runner: Callable[..., Any] = run_and_report,
) -> Any:
    """Создаёт блок с кнопкой; вывод — в `output` (QPlainTextEdit), статус — в `status` (QLabel).

    Переход к странице средства идёт через `focus_discovery_target` главного окна,
    если оно есть; вне главного окна кнопки средств просто не показываются.
    """

    container = QtWidgets.QWidget()
    container_layout = QtWidgets.QVBoxLayout(container)
    container_layout.setContentsMargins(0, 0, 0, 0)
    container_layout.setSpacing(6)
    button = QtWidgets.QPushButton(NET_VERDICT_BUTTON_TEXT)
    button.setObjectName(NET_VERDICT_BUTTON_OBJECT_NAME)
    button.setMinimumHeight(30)
    button.setToolTip(
        "Ping шлюза и 1.1.1.1/8.8.8.8, маршруты, DNS, HTTPS к контрольному и заблокированным хостам; "
        "вердикт: локальная сеть / провайдер / DNS / DPI. Гипотеза на текущий момент."
    )

    remedies_box = QtWidgets.QFrame()
    remedies_box.setObjectName(NET_VERDICT_REMEDIES_OBJECT_NAME)
    remedies_layout = QtWidgets.QHBoxLayout(remedies_box)
    remedies_layout.setContentsMargins(0, 0, 0, 0)
    remedies_layout.setSpacing(6)
    remedies_box.setVisible(False)
    container_layout.addWidget(button)
    container_layout.addWidget(remedies_box)

    class _Worker(QtCore.QThread):
        finished_text = QtCore.pyqtSignal(str, str)

        def run(self) -> None:  # pragma: no cover - runs in GUI thread pool
            code = ""
            try:
                text, path = runner(root=root)
                code = verdict_code_from_report(path)
            except Exception as exc:
                text = f"Диагностика сети: ошибка\n{exc}"
            self.finished_text.emit(text, code)

    holder: dict[str, Any] = {}

    def go_to(page_key: str) -> None:
        window = container.window()
        navigate = getattr(window, "focus_discovery_target", None)
        if callable(navigate):
            navigate(page_key, None)

    def show_remedies(code: str) -> None:
        while remedies_layout.count():
            item = remedies_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        remedies = remedies_for_verdict(code)
        if not remedies:
            remedies_box.setVisible(False)
            return
        caption = QtWidgets.QLabel("Что попробовать:")
        caption.setObjectName("mutedText")
        remedies_layout.addWidget(caption)
        can_navigate = callable(getattr(container.window(), "focus_discovery_target", None))
        for remedy in remedies:
            if remedy.page_key and can_navigate:
                widget = QtWidgets.QPushButton(remedy.title + " →")
                widget.clicked.connect(lambda _checked=False, key=remedy.page_key: go_to(key))
            else:
                widget = QtWidgets.QLabel(remedy.title)
            widget.setObjectName(f"netVerdictRemedy-{remedy.key}")
            widget.setToolTip(remedy_hint(remedy))
            remedies_layout.addWidget(widget)
        remedies_layout.addStretch(1)
        remedies_box.setVisible(True)

    def on_done(text: str, code: str = "") -> None:
        show_remedies(code)
        output.setPlainText(text)
        first = text.splitlines()[0] if text else ""
        status.setText("Статус: " + (first or "диагностика сети завершена"))
        button.setEnabled(True)
        holder.pop("worker", None)

    def start() -> None:
        if holder.get("worker") is not None:
            return
        if is_busy is not None and is_busy():
            output.setPlainText("Blockcheck уже выполняется. Диагностика сети исказится — дождитесь завершения.")
            return
        button.setEnabled(False)
        status.setText("Статус: диагностика сети… (около 15–30 с)")
        worker = _Worker()
        worker.finished_text.connect(on_done)
        holder["worker"] = worker
        worker.start()

    button.clicked.connect(lambda _checked=False: start())
    container.show_remedies = show_remedies
    return container
