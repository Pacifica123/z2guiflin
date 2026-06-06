"""Graphical sudo askpass helper for Zap2 GUI.

Этот модуль запускается только как ``SUDO_ASKPASS`` helper. Он показывает
локальный графический диалог, печатает введённый пароль в stdout для ``sudo -A``
и сразу завершается. Пароль не пишется в логи, файлы или runtime-state.
"""

from __future__ import annotations

import os
import subprocess
import sys
from typing import Callable


def _prompt_text() -> str:
    return os.environ.get(
        "ZAP2_SUDO_ASKPASS_PROMPT",
        "Введите пароль sudo для Zap2 GUI",
    )


def _try_pyqt6_prompt() -> str | None:
    try:
        from PyQt6.QtWidgets import QApplication, QInputDialog, QLineEdit
    except Exception:
        return None

    app = QApplication.instance() or QApplication([])
    text, ok = QInputDialog.getText(
        None,
        "Zap2: sudo",
        _prompt_text(),
        QLineEdit.EchoMode.Password,
    )
    if not ok:
        return None
    return str(text)


def _try_tk_prompt() -> str | None:
    try:
        import tkinter as tk
        from tkinter import simpledialog
    except Exception:
        return None

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        return simpledialog.askstring("Zap2: sudo", _prompt_text(), show="*", parent=root)
    finally:
        root.destroy()


def _try_zenity_prompt() -> str | None:
    zenity = _which("zenity")
    if not zenity:
        return None
    completed = subprocess.run(
        [zenity, "--password", "--title", "Zap2: sudo"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if completed.returncode != 0:
        return None
    return completed.stdout.rstrip("\n")


def _which(name: str) -> str | None:
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        if not directory:
            continue
        candidate = os.path.join(directory, name)
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


def _prompt_password() -> str | None:
    # Prefer PyQt because the main application is PyQt-based. Zenity/Tk are only
    # fallbacks for environments where the helper is executed outside the main
    # process or PyQt is unavailable to the askpass interpreter.
    for backend in (_try_pyqt6_prompt, _try_zenity_prompt, _try_tk_prompt):
        value = backend()
        if value:
            return value
    return None


def main(argv: list[str] | None = None) -> int:
    password = _prompt_password()
    if not password:
        return 1
    sys.stdout.write(password + "\n")
    sys.stdout.flush()
    return 0


if __name__ == "__main__":  # pragma: no cover - launched by sudo -A
    raise SystemExit(main(sys.argv[1:]))
