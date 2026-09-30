#!/usr/bin/env python3
"""Проверка v0.3-beta Stage 2 build dependency preflight без установки пакетов."""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "gui"))


def _write_headers(include_root: Path) -> None:
    for relative in (
        "zlib.h",
        "libnetfilter_queue/libnetfilter_queue.h",
        "libnfnetlink/libnfnetlink.h",
        "libmnl/libmnl.h",
        "luajit-2.1/lua.h",
    ):
        path = include_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("/* fake header for preflight check */\n", encoding="utf-8")


def main() -> int:
    from zap2_gui.adapters.build_dependencies import (
        BUILD_DEPENDENCY_MARKER,
        build_dependency_requirements_for_target,
        run_build_dependency_preflight,
    )

    with tempfile.TemporaryDirectory(prefix="zap2-build-deps-check-") as temp_dir:
        include_root = Path(temp_dir) / "include"
        _write_headers(include_root)
        ok = run_build_dependency_preflight(
            "nfqws2",
            include_paths=(include_root,),
            command_resolver=lambda command: f"/fake/bin/{command}",
        )
        if not ok.ok:
            print("Synthetic dependency preflight должен проходить")
            print(ok.to_text())
            return 1
        if ok.marker != BUILD_DEPENDENCY_MARKER:
            print("Неожиданный marker build dependency preflight")
            return 1

        missing = run_build_dependency_preflight(
            "nfqws2",
            include_paths=(include_root,),
            command_resolver=lambda command: None if command in {"make", "cc", "gcc", "clang"} else f"/fake/bin/{command}",
        )
        if missing.ok or not any(check.check_id == "make" for check in missing.missing_required):
            print("Preflight должен обнаруживать отсутствие make/toolchain")
            return 1

        requirements = build_dependency_requirements_for_target("nfqws2")
        if requirements.get("executesInstallNow") is not False or requirements.get("runsMakeNow") is not False:
            print("Dependency requirements должны быть read-only")
            return 1
        if "libnetfilter_queue" not in str(requirements):
            print("Dependency requirements должны явно включать libnetfilter_queue")
            return 1

    adapter_text = (ROOT / "gui/zap2_gui/adapters/build_dependencies.py").read_text(encoding="utf-8")
    for forbidden in ("subprocess", "os.system", "Popen", "install_prereq", "install_easy"):
        if forbidden in adapter_text:
            print(f"Build dependency preflight не должен выполнять shell/install fragments: {forbidden}")
            return 1
    if "apt install" not in adapter_text or "dnf install" not in adapter_text or "pacman -S" not in adapter_text:
        print("Preflight должен содержать owner action hints для популярных дистрибутивов")
        return 1

    cli = shutil.which("python") or sys.executable
    if not (ROOT / "docs/history/stages/BUILD_DEPENDENCY_PREFLIGHT.md").exists():
        print("Документация build dependency preflight отсутствует")
        return 1
    print(f"Build dependency preflight v0.3-beta Stage 2 OK; python={cli}; пакеты не устанавливаются")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
