#!/usr/bin/env python3
"""Bounded full-regression orchestrator for P04c acceptance.

The historical suite contains slow integration-style files and a few tests that
intentionally mutate ``ROOT/.zap2``. P04c therefore never executes that corpus
against the live checkout. Every worker gets an isolated project copy and a
sandboxed HOME/XDG environment. The complete ``tests/test_*.py`` corpus is
partitioned deterministically into four disjoint workers and every worker must
return zero.
"""
from __future__ import annotations

import concurrent.futures
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_ROOT = PROJECT_ROOT / "tests"
WORKERS = 4
COPY_IGNORE = shutil.ignore_patterns(
    ".git",
    ".zap2",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "*.pyc",
    "*.pyo",
)


def _partition(items: list[str], count: int) -> list[list[str]]:
    width, remainder = divmod(len(items), count)
    groups: list[list[str]] = []
    start = 0
    for index in range(count):
        size = width + (1 if index < remainder else 0)
        groups.append(items[start : start + size])
        start += size
    return groups


def _run_group(index: int, tests: list[str], work_root: Path) -> tuple[int, int, Path]:
    worker_root = work_root / f"worker-{index:02d}"
    project = worker_root / "project"
    home = worker_root / "home"
    temp_dir = worker_root / "tmp"
    log_path = work_root / f"group-{index:02d}.log"
    shutil.copytree(PROJECT_ROOT, project, ignore=COPY_IGNORE)
    home.mkdir(parents=True, exist_ok=True)
    temp_dir.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["HOME"] = str(home)
    env["XDG_CONFIG_HOME"] = str(home / ".config")
    env["XDG_DATA_HOME"] = str(home / ".local" / "share")
    env["XDG_CACHE_HOME"] = str(home / ".cache")
    env["TMPDIR"] = str(temp_dir)
    env["TEMP"] = str(temp_dir)
    env["TMP"] = str(temp_dir)
    env["PYTHONPATH"] = str(project / "gui")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    command = [sys.executable, "-m", "pytest", "-q", *tests]
    result = subprocess.run(
        command,
        cwd=project,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    log_path.write_text(result.stdout or "", encoding="utf-8")
    return index, result.returncode, log_path


def main() -> int:
    tests = [path.relative_to(PROJECT_ROOT).as_posix() for path in sorted(TEST_ROOT.glob("test_*.py"))]
    if not tests:
        print("P04c regression: FAIL — test corpus is empty", file=sys.stderr)
        return 2
    groups = _partition(tests, WORKERS)
    flattened = [item for group in groups for item in group]
    if any(not group for group in groups) or flattened != tests or len(set(flattened)) != len(tests):
        print("P04c regression: FAIL — partition does not cover test corpus exactly once", file=sys.stderr)
        return 2

    with tempfile.TemporaryDirectory(prefix="zap2-p04c-regression-") as temp:
        work_root = Path(temp)
        results: list[tuple[int, int, Path]] = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as pool:
            futures = [pool.submit(_run_group, index + 1, group, work_root) for index, group in enumerate(groups)]
            for future in concurrent.futures.as_completed(futures):
                results.append(future.result())
        results.sort()
        failed = [item for item in results if item[1] != 0]
        for index, returncode, log_path in results:
            lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
            tail_size = 80 if returncode else 4
            print(f"group {index}/{WORKERS}: files={len(groups[index - 1])}; rc={returncode}")
            for line in lines[-tail_size:]:
                print(f"  {line}")
        if failed:
            print("P04c regression: FAIL", file=sys.stderr)
            return 1

    print(f"P04c regression: PASS ({len(tests)} files, {WORKERS} isolated workers)")
    print("live checkout mutations: none (tests executed in temporary project copies)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
