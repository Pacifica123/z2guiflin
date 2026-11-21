"""Жизненный цикл коротких и длительных QThread-задач GUI.

Qt-импорты выполняются только при вызове: модуль можно импортировать без PyQt.
Задания работают в отдельном потоке, а UI-callbacks — после QThread.finished
в потоке приложения. Реестр принадлежит QApplication, а не закрываемой странице.
"""

from __future__ import annotations

import traceback
from typing import Any, Callable


def task_manager(QtCore: Any) -> Any:
    """Реестр живых потоков, сохраняющий их до подтверждённого завершения."""

    app = QtCore.QCoreApplication.instance()
    if app is None:
        raise RuntimeError("Для запуска фоновой задачи сначала создайте QApplication")
    manager = getattr(app, "_zap2_task_manager", None)
    if manager is not None:
        return manager

    class _Manager(QtCore.QObject):
        def __init__(self) -> None:
            super().__init__(app)
            self._active: dict[Any, Any] = {}
            self._idle_callbacks: list[Callable[[], None]] = []
            app.aboutToQuit.connect(self._drain_on_quit)

        @property
        def active_count(self) -> int:
            return len(self._active)

        def when_idle(self, callback: Callable[[], None]) -> None:
            if self._active:
                self._idle_callbacks.append(callback)
            else:
                QtCore.QTimer.singleShot(0, callback)

        def _release(self, worker: Any) -> None:
            self._active.pop(worker, None)
            if not self._active:
                callbacks, self._idle_callbacks = self._idle_callbacks, []
                for callback in callbacks:
                    QtCore.QTimer.singleShot(0, callback)

        def _drain_on_quit(self) -> None:
            # Fallback для app.quit()/выхода в обход MainWindow.closeEvent.
            # run() не запускает event loop, поэтому quit() не поможет.
            # Не используем terminate(): сетевой/системный job должен завершиться сам.
            for worker in tuple(self._active):
                worker.requestInterruption()
                worker.wait()
            self._active.clear()
            self._idle_callbacks.clear()

    manager = _Manager()
    app._zap2_task_manager = manager
    return manager


def start_background_task(
    QtCore: Any,
    owner: Any,
    job: Callable[[Callable[[str], None]], Any],
    *,
    completed: Callable[[Any], None],
    failed: Callable[[Exception], None] | None = None,
    progress: Callable[[str], None] | None = None,
) -> Any:
    """Запустить job(report) без риска уничтожить работающий QThread.

    Обработчики результата выполняются только после QThread.finished + wait(),
    в GUI-потоке. Если owner уничтожен, обработчики не вызываются.
    """

    manager = task_manager(QtCore)

    class _Worker(QtCore.QThread):  # type: ignore[misc, valid-type]
        line = QtCore.pyqtSignal(str)

        def __init__(self) -> None:
            super().__init__()  # Нельзя делать owner родителем QThread: он может исчезнуть раньше.
            self.value: Any = None
            self.error: Exception | None = None

        def run(self) -> None:  # pragma: no cover - отдельный поток
            try:
                self.value = job(self.line.emit)
            except Exception as exc:  # noqa: BLE001 - ошибка передаётся в GUI-поток
                self.error = exc

    class _Receiver(QtCore.QObject):
        def __init__(self, worker: Any) -> None:
            super().__init__(manager)
            self.worker = worker
            self.detached = False
            self.on_done = completed
            self.on_fail = failed
            self.on_line = progress

        @QtCore.pyqtSlot()
        def owner_gone(self) -> None:
            self.detached = True
            self.on_done = None
            self.on_fail = None
            self.on_line = None

        @QtCore.pyqtSlot(str)
        def report_line(self, line: str) -> None:
            if not self.detached and self.on_line is not None:
                try:
                    self.on_line(line)
                except Exception:  # noqa: BLE001
                    traceback.print_exc()

        @QtCore.pyqtSlot()
        def thread_finished(self) -> None:
            worker = self.worker
            # finished испускается до окончательной очистки TLS: wait() — барьер.
            worker.wait()
            manager._release(worker)
            try:
                if not self.detached:
                    if worker.error is not None:
                        if self.on_fail is not None:
                            self.on_fail(worker.error)
                        else:
                            traceback.print_exception(worker.error)
                    elif self.on_done is not None:
                        self.on_done(worker.value)
            except Exception:  # noqa: BLE001 - исключения слотов PyQt могут abort() процесс
                traceback.print_exc()
            finally:
                self.owner_gone()
                self.worker = None
                worker.deleteLater()
                self.deleteLater()

    worker = _Worker()
    receiver = _Receiver(worker)
    worker.line.connect(receiver.report_line, QtCore.Qt.ConnectionType.QueuedConnection)
    worker.finished.connect(receiver.thread_finished, QtCore.Qt.ConnectionType.QueuedConnection)
    owner.destroyed.connect(receiver.owner_gone)
    manager._active[worker] = receiver
    worker.start()
    return worker


def current_task_interrupted(QtCore: Any) -> bool:
    """Cooperate with the task manager's requestInterruption on app quit."""
    return bool(QtCore.QThread.currentThread().isInterruptionRequested())


__all__ = ["task_manager", "start_background_task", "current_task_interrupted"]
