"""Кнопка «Диагностика сети (вердикт)» для Blockcheck lab.

Самодостаточный модуль: замер идёт в QThread, UI не блокируется. Без sudo и
без изменений firewall; результат — текст вердикта и JSON в `.zap2/runtime/reports`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Optional

from ..adapters.net_verdict import run_and_report

NET_VERDICT_BUTTON_TEXT = "Диагностика сети (вердикт)"
NET_VERDICT_BUTTON_OBJECT_NAME = "blockcheckNetVerdictButton"


def make_net_verdict_button(
    QtCore: Any,
    QtWidgets: Any,
    output: Any,
    status: Any,
    root: Optional[Path] = None,
    is_busy: Optional[Callable[[], bool]] = None,
    runner: Callable[..., Any] = run_and_report,
) -> Any:
    """Создаёт кнопку; вывод — в `output` (QPlainTextEdit), статус — в `status` (QLabel)."""

    button = QtWidgets.QPushButton(NET_VERDICT_BUTTON_TEXT)
    button.setObjectName(NET_VERDICT_BUTTON_OBJECT_NAME)
    button.setMinimumHeight(30)
    button.setToolTip(
        "Ping шлюза и 1.1.1.1/8.8.8.8, маршруты, DNS, HTTPS к контрольному и заблокированным хостам; "
        "вердикт: локальная сеть / провайдер / DNS / DPI. Гипотеза на текущий момент."
    )

    class _Worker(QtCore.QThread):
        finished_text = QtCore.pyqtSignal(str)

        def run(self) -> None:  # pragma: no cover - runs in GUI thread pool
            try:
                text, _path = runner(root=root)
            except Exception as exc:
                text = f"Диагностика сети: ошибка\n{exc}"
            self.finished_text.emit(text)

    holder: dict[str, Any] = {}

    def on_done(text: str) -> None:
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
    return button
