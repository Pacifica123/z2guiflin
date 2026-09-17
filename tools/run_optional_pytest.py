#!/usr/bin/env python3
"""Run pytest when it is already installed; otherwise report an explicit skip.

Pytest is a development-only dependency for this source workspace and must not
become a hidden prerequisite for applying a devctl product patch.
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys


def main() -> int:
    if importlib.util.find_spec("pytest") is None:
        print("pytest is not installed; optional pytest regression suite skipped")
        return 0
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    current = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = "gui" if not current else f"gui{os.pathsep}{current}"
    command = [sys.executable, "-m", "pytest", "-q", *(sys.argv[1:] or ["tests"])]
    print("running optional pytest regression:", " ".join(command))
    return subprocess.call(command, env=env)


if __name__ == "__main__":
    raise SystemExit(main())
