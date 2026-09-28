from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from zap2_gui.adapters.core_generation import generation_identity_errors, sha256_file

ROOT = Path(__file__).resolve().parents[1]


def _copy_project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    shutil.copytree(
        ROOT,
        project,
        ignore=shutil.ignore_patterns(".git", ".zap2", ".pytest_cache", "__pycache__", "*.pyc"),
    )
    return project


def _fake_make(tmp_path: Path, *, exit_code: int) -> Path:
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    script = bindir / "make"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import os, pathlib, stat, sys\n"
        "target = sys.argv[1] if len(sys.argv) > 1 else 'all'\n"
        "cwd = pathlib.Path.cwd()\n"
        "if cwd.name == 'nfq2' or target == 'nfqws2':\n"
        "    p = cwd / 'nfqws2'\n"
        "    p.write_text('#!/bin/sh\\necho p03-staged\\n')\n"
        "    p.chmod(p.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)\n"
        f"raise SystemExit({exit_code})\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    return bindir


def _run_adapter(project: Path, bindir: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PATH"] = f"{bindir}:{env.get('PATH', '')}"
    return subprocess.run(
        [sys.executable, str(project / "tools/core_generation_build.py"), "nfqws2"],
        cwd=project,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def test_p03_staged_build_applies_transform_without_mutating_pinned_source(tmp_path: Path) -> None:
    project = _copy_project(tmp_path)
    base = project / "core/zapret2/nfq2/nfqws.c"
    base_hash = sha256_file(base)
    transform = project / "core/overlays/zapret2/source/nfq2/nfqws.c"
    effective_hash = sha256_file(transform)
    bindir = _fake_make(tmp_path, exit_code=0)

    result = _run_adapter(project, bindir)

    assert result.returncode == 0, result.stderr
    assert sha256_file(base) == base_hash
    assert not generation_identity_errors(project)
    binary = project / "core/zapret2/nfq2/nfqws2"
    assert binary.is_file() and os.access(binary, os.X_OK)
    stages = list((project / ".zap2/build/core-generation").glob("*/source/nfq2/nfqws.c"))
    assert len(stages) == 1
    assert sha256_file(stages[0]) == effective_hash
    effective = stages[0].read_text(encoding="utf-8")
    assert effective.index("nfq_init(&h, &qh, &cbdata)") < effective.index("droproot(params.uid")


def test_p03_failed_staged_build_does_not_publish_partial_binary(tmp_path: Path) -> None:
    project = _copy_project(tmp_path)
    base = project / "core/zapret2/nfq2/nfqws.c"
    base_hash = sha256_file(base)
    binary = project / "core/zapret2/nfq2/nfqws2"
    binary.write_bytes(b"previous-good-binary")
    binary.chmod(0o755)
    previous_hash = sha256_file(binary)
    bindir = _fake_make(tmp_path, exit_code=9)

    result = _run_adapter(project, bindir)

    assert result.returncode == 9
    assert sha256_file(base) == base_hash
    assert sha256_file(binary) == previous_hash
    assert not generation_identity_errors(project)
