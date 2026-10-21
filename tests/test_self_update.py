from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from zap2_gui.adapters.self_update import CommandResult, check_update, checkout_release_digest, run_command, run_update

ROOT = Path(__file__).resolve().parents[1]


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=cwd, check=True, capture_output=True)


def _checkout(tmp: Path) -> tuple[Path, Path]:
    origin = tmp / "origin"
    origin.mkdir()
    (origin / "meta_tools").mkdir()
    (origin / "packaging").mkdir()
    (origin / "meta_tools/build_local_package.sh").write_text("#!/bin/sh\n")
    (origin / "pyproject.toml").write_text('version = "9.1.0"\n')
    (origin / "a.txt").write_text("one")
    (origin / "packaging/release-files.json").write_text(json.dumps({"schemaVersion": 1, "files": ["a.txt", "meta_tools/build_local_package.sh"]}))
    _git(origin, "init", "-q", "-b", "main")
    _git(origin, "add", "-A")
    _git(origin, "commit", "-qm", "one")
    clone = tmp / "clone"
    _git(tmp, "clone", "-q", str(origin), str(clone))
    return origin, clone


def test_digest_matches_release_builder_on_real_tree() -> None:
    import sys

    sys.path.insert(0, str(ROOT / "packaging"))
    import build_release

    files = build_release.source_files(ROOT)
    records = {p.relative_to(ROOT).as_posix(): {"sha256": __import__("hashlib").sha256(p.read_bytes()).hexdigest(), "mode": 0o755 if p.suffix == ".sh" or p.name == "zap2-runtime-executor" else 0o644} for p in files}
    expected = __import__("hashlib").sha256(json.dumps(records, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    assert checkout_release_digest(ROOT)[1] == expected


def test_new_remote_commits_and_content_drift_are_reported(tmp_path: Path) -> None:
    origin, clone = _checkout(tmp_path)
    version, digest = checkout_release_digest(clone)
    env = {"ZAP2_INSTALLED_ROOT": str(tmp_path / "pkg")}
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg/RELEASE_MANIFEST.json").write_text(json.dumps({"version": version, "releaseDigest": digest}))
    status = check_update(clone, environ=env)
    assert not status.available and status.behind == 0, status.to_text()

    (origin / "a.txt").write_text("two")
    _git(origin, "commit", "-qam", "второй коммит")
    status = check_update(clone, environ=env)
    assert status.behind == 1 and "второй коммит" in status.new_commits[0] and status.available

    _git(clone, "pull", "-q", "--ff-only", "origin", "main")
    status = check_update(clone, environ=env)
    assert status.behind == 0 and status.content_differs and status.available
    assert "пересобрать" in status.to_text()


def test_missing_checkout_is_explained() -> None:
    status = check_update(None, environ={})
    assert not status.available and "checkout" in status.errors[0]


def test_update_stops_runtime_first_and_runs_steps_in_order(tmp_path: Path, monkeypatch) -> None:
    _origin, clone = _checkout(tmp_path)
    workspace = tmp_path / "ws"
    session = workspace / ".zap2/runtime/sessions/default.owner-rules.json"
    session.parent.mkdir(parents=True)
    session.write_text(json.dumps({"state": "applied"}))
    calls: list[list[str]] = []

    def runner(argv, cwd, timeout):
        calls.append(list(argv))
        if argv[0] == "makepkg":
            (cwd / "zap2gui-linux-9.1.0-1-x86_64.pkg.tar.zst").write_text("pkg")
        if argv[0] == "git":
            return run_command(argv, cwd, timeout)  # настоящий git на временном репозитории
        return CommandResult(0, "ok")

    def stop() -> str:
        session.write_text(json.dumps({"state": "reverted"}))
        return "stopped"

    log: list[str] = []
    assert run_update(clone, log=log.append, stop_runtime=stop, runner=runner, workspace=workspace, build_dir=tmp_path / "out")
    tools = [c[0] for c in calls if c[0] != "git"]
    assert tools == ["bash", "makepkg", "pkexec"]
    assert calls[-1][:4] == ["pkexec", "pacman", "-U", "--noconfirm"]
    assert log[0].startswith("1/5") and "stopped" in log


def test_update_aborts_when_runtime_does_not_stop(tmp_path: Path) -> None:
    _origin, clone = _checkout(tmp_path)
    workspace = tmp_path / "ws"
    session = workspace / ".zap2/runtime/sessions/default.owner-rules.json"
    session.parent.mkdir(parents=True)
    session.write_text(json.dumps({"state": "applied"}))
    calls: list[list[str]] = []
    log: list[str] = []
    ok = run_update(clone, log=log.append, stop_runtime=lambda: "stop failed", runner=lambda a, c, t: calls.append(list(a)) or CommandResult(0, ""), workspace=workspace)
    assert not ok and calls == [] and "отменена" in log[-1]


def test_update_dialog_renders_offscreen(tmp_path: Path, monkeypatch) -> None:
    pytest.importorskip("PyQt6")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtCore import QSettings
    from PyQt6.QtWidgets import QApplication, QCheckBox, QLineEdit, QPushButton
    from zap2_gui.widgets.update_dialog import auto_check_due, make_update_dialog

    app = QApplication.instance() or QApplication([])
    settings = QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)
    assert auto_check_due(settings)
    settings.setValue("update/last-check", 10_000.0)
    assert not auto_check_due(settings, now=10_000.0 + 60)
    dialog = make_update_dialog(None, settings, ROOT, lambda: "")
    assert dialog.findChild(QLineEdit, "updateCheckoutPath").text() in {str(ROOT), ""}
    assert not dialog.findChild(QPushButton, "updateRunButton").isEnabled()
    dialog.findChild(QCheckBox, "updateAutoCheck").setChecked(False)
    assert settings.value("update/auto-check") == "false"
    dialog.close()
    app.processEvents()
