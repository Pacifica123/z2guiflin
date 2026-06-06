from __future__ import annotations

from pathlib import Path

from zap2_gui.adapters.build_dependencies import (
    BUILD_DEPENDENCY_MARKER,
    build_dependency_requirements_for_target,
    make_success_report,
    run_build_dependency_preflight,
)


def _write_headers(include_root: Path, *, omit: set[str] | None = None) -> None:
    omitted = omit or set()
    headers = {
        "zlib": "zlib.h",
        "libnetfilter_queue": "libnetfilter_queue/libnetfilter_queue.h",
        "libnfnetlink": "libnfnetlink/libnfnetlink.h",
        "libmnl": "libmnl/libmnl.h",
        "lua": "luajit-2.1/lua.h",
    }
    for key, relative in headers.items():
        if key in omitted:
            continue
        path = include_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("/* fake header */\n", encoding="utf-8")


def test_dependency_preflight_detects_missing_libnetfilter_queue_header(tmp_path: Path) -> None:
    include_root = tmp_path / "include"
    _write_headers(include_root, omit={"libnetfilter_queue"})
    report = run_build_dependency_preflight(
        "nfqws2",
        include_paths=(include_root,),
        command_resolver=lambda command: f"/fake/{command}",
    )

    assert report.marker == BUILD_DEPENDENCY_MARKER
    assert report.ok is False
    assert any(check.check_id == "libnetfilter_queue" for check in report.missing_required)
    assert "apt install" in report.to_text()
    assert report.executes_install_now is False
    assert report.runs_make_now is False


def test_dependency_preflight_can_pass_with_synthetic_headers_and_commands(tmp_path: Path) -> None:
    include_root = tmp_path / "include"
    _write_headers(include_root)
    report = run_build_dependency_preflight(
        "nfqws2",
        include_paths=(include_root,),
        command_resolver=lambda command: f"/fake/{command}",
    )

    assert report.ok is True
    assert not report.missing_required
    assert all(check.status == "ok" for check in report.checks)


def test_dependency_requirements_are_hash_stable_and_not_host_status() -> None:
    requirements = build_dependency_requirements_for_target("nfqws2")

    assert requirements["target"] == "nfqws2"
    assert requirements["executesInstallNow"] is False
    assert requirements["requiresSudoNow"] is False
    assert requirements["runsMakeNow"] is False
    assert "libnetfilter_queue" in str(requirements)
    assert "found" not in str(requirements)


def test_make_success_report_is_for_fake_runner_tests_only() -> None:
    report = make_success_report()

    assert report.ok is True
    assert report.marker == BUILD_DEPENDENCY_MARKER
    assert all(check.details == "synthetic test dependency satisfied" for check in report.checks)
