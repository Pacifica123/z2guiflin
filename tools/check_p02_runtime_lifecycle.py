#!/usr/bin/env python3
"""Dependency-free P02 smoke for devctl.

This check intentionally uses only the standard library plus the project
package.  It does not require pytest/root/nft privileges and must not mutate the
source workspace.  Privileged L3/S-INSTALL remains a separate UserTestSpace
owner check.
"""
from __future__ import annotations

import json
import runpy
import shutil
import tempfile
from pathlib import Path

from zap2_gui.adapters.gui_privilege import build_gui_privileged_command
from zap2_gui.adapters.runtime_apply import RuntimeCommandResult, reconcile_runtime_owner_rules
from zap2_gui.adapters.runtime_default import default_workflow_status
from zap2_gui.adapters.runtime_kernel import runtime_kernel_status

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "tools/privileged/zap2-runtime-executor"


def _missing_nft(argv: tuple[str, ...]) -> RuntimeCommandResult:
    return RuntimeCommandResult(argv=argv, returncode=1, stderr="No such table")


def _assert_helper_contract() -> None:
    text = HELPER.read_text(encoding="utf-8")
    assert text.startswith("#!/usr/bin/python3 -I")
    assert "import zap2_gui" not in text
    assert "shell=True" not in text
    assert "PYTHONPATH" in text  # explicit deny-list, not an import path

    helper = runpy.run_path(str(HELPER), run_name="p02_dependency_free_smoke")
    stable_json = helper["stable_json"]
    sha256_bytes = helper["sha256_bytes"]
    parse_request = helper["parse_request"]
    execute = helper["execute"]
    ExecutorError = helper["ExecutorError"]

    body = {
        "schemaVersion": 1,
        "protocol": "zap2-privilege-plan/v1",
        "actionId": "unknown.action",
        "payload": {},
    }
    request_hash = sha256_bytes(stable_json(body).encode("utf-8"))
    wire = dict(body, requestHash=request_hash)
    action_id, payload, calculated = parse_request((stable_json(wire) + "\n").encode("utf-8"), request_hash)
    assert action_id == "unknown.action"
    assert payload == {}
    assert calculated == request_hash
    try:
        execute(action_id, payload)
    except ExecutorError:
        pass
    else:
        raise AssertionError("finite helper unexpectedly accepted unknown actionId")


def _assert_outside_checkout_read_only() -> None:
    with tempfile.TemporaryDirectory(prefix="zap2-p02-smoke-") as raw:
        project = Path(raw) / "project"
        shutil.copytree(
            ROOT,
            project,
            ignore=shutil.ignore_patterns(
                ".git", ".zap2", ".pytest_cache", "__pycache__", "*.pyc", "*.pyo", ".uts-venv"
            ),
        )
        runtime_root = project / ".zap2"
        assert not runtime_root.exists()

        preview = build_gui_privileged_command(root=project, action="start")
        joined = " ".join(preview.argv)
        assert preview.argv[:3] == ("sudo", "-A", "--")
        assert "/usr/local/libexec/zap2-runtime-executor" in preview.argv
        assert "zap2_gui.app" not in joined
        assert "PYTHONPATH" not in joined
        assert not runtime_root.exists(), "read-only privilege preview created runtime state"

        reconciled = reconcile_runtime_owner_rules(project, runner=_missing_nft)
        assert reconciled.state == "clean"
        assert not runtime_root.exists(), "read-only reconcile created runtime state"

        status = runtime_kernel_status(
            project,
            nft_runner=_missing_nft,
            executor_path=project / "tools/privileged/zap2-runtime-executor",
        )
        assert status.ownership_state == "absent"
        assert not runtime_root.exists(), "read-only kernel status created runtime state"

        default_status = default_workflow_status(project)
        assert default_status.workflow_state == "not-started"
        assert not runtime_root.exists(), "read-only default status created runtime state"


def main() -> int:
    _assert_helper_contract()
    _assert_outside_checkout_read_only()
    print(json.dumps({"ok": True, "check": "P02 dependency-free lifecycle/privilege smoke", "groups": 2}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
