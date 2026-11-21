"""P0 regression: QThread сохраняется до Qt.finished и не трогает умерший UI."""

from __future__ import annotations

import ast
from pathlib import Path
import time

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_qthread_only_created_in_managed_module() -> None:
    """Новые QThread.start вне общего реестра снова введут abort при закрытии."""
    gui = ROOT / "gui" / "zap2_gui"
    raw = [
        path.relative_to(gui).as_posix()
        for path in gui.rglob("*.py")
        if path.name != "qt_background.py"
        and any(isinstance(node, ast.Attribute) and node.attr == "QThread"
                for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))))
    ]
    assert raw == []


def test_qt_task_module_is_importable_without_pyqt() -> None:
    from zap2_gui.qt_background import start_background_task, task_manager

    assert callable(start_background_task) and callable(task_manager)


def _qt_app(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def _pump(app, predicate, timeout: float = 4.0) -> None:
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.003)
    app.processEvents()
    assert predicate(), "Не завершилось фоновое задание Qt"


def test_qthread_completion_after_exit_and_repeated_starts(monkeypatch) -> None:
    app = _qt_app(monkeypatch)
    from PyQt6 import QtCore
    from PyQt6.QtWidgets import QWidget
    from zap2_gui.qt_background import start_background_task, task_manager

    owner = QWidget()
    manager = task_manager(QtCore)
    complete: list[int] = []
    errors: list[str] = []
    finished_running: list[bool] = []
    gui_thread = QtCore.QThread.currentThread()

    for i in range(50):
        task = start_background_task(
            QtCore, owner, lambda _report, index=i: index,
            completed=lambda value: (complete.append(value),
                                     finished_running.append(task.isRunning()),
                                     errors.append("wrong callback thread")
                                     if QtCore.QThread.currentThread() != gui_thread else None),
            failed=lambda exc: errors.append(str(exc)),
        )
        _pump(app, lambda: len(complete) == i + 1)
        assert manager.active_count == 0
    assert complete == list(range(50)) and not errors
    assert finished_running == [False] * 50


def test_qthread_owner_destroyed_before_completion(monkeypatch) -> None:
    app = _qt_app(monkeypatch)
    from PyQt6 import QtCore
    from PyQt6.QtWidgets import QWidget
    from zap2_gui.qt_background import start_background_task, task_manager

    owner = QWidget()
    completed: list[object] = []
    started = __import__("threading").Event()
    release = __import__("threading").Event()

    def job(_report):
        started.set()
        assert release.wait(3)
        return "ready"

    start_background_task(QtCore, owner, job, completed=completed.append)
    assert started.wait(2)
    owner.deleteLater()
    QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
    release.set()
    _pump(app, lambda: task_manager(QtCore).active_count == 0)
    assert completed == []


def test_qthread_error_and_progress_return_to_gui(monkeypatch) -> None:
    app = _qt_app(monkeypatch)
    from PyQt6 import QtCore
    from PyQt6.QtWidgets import QWidget
    from zap2_gui.qt_background import start_background_task, task_manager

    owner = QWidget()
    lines: list[str] = []
    failures: list[str] = []
    main_thread = QtCore.QThread.currentThread()

    def job(report):
        report("step")
        raise ValueError("failure")

    start_background_task(QtCore, owner, job,
                          completed=lambda _result: pytest.fail("unexpected success"),
                          failed=lambda exc: failures.append(str(exc)),
                          progress=lambda line: (lines.append(line),
                                                 assert_gui_thread()))

    def assert_gui_thread() -> None:
        assert QtCore.QThread.currentThread() == main_thread

    _pump(app, lambda: len(failures) == 1 and task_manager(QtCore).active_count == 0)
    assert lines == ["step"] and failures == ["failure"]
