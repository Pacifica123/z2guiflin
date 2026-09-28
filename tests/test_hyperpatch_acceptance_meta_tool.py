from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "meta_tools/hyperpatch_acceptance.sh"


def test_hyperpatch_acceptance_script_is_valid_bash_and_owner_only() -> None:
    result = subprocess.run(["bash", "-n", str(SCRIPT)], text=True, capture_output=True, check=False)
    assert result.returncode == 0, result.stderr
    text = SCRIPT.read_text(encoding="utf-8")
    assert '"$(id -u)" -eq 0' in text
    assert "Acceptance runner нельзя запускать целиком через sudo/root" in text


def test_p03_acceptance_covers_generation_build_parser_privilege_runtime_and_cleanup() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    required_fragments = (
        "check_p03_core_generation.py",
        "inventory_core.py --check",
        "uts_prepare.sh --p03",
        "check_project_tree.py",
        "import PyQt6",
        "--default-build-deps",
        "--default-build-plan",
        "--default-build --confirm",
        "core-build-receipt.json",
        "--strategy-parser-preflight",
        "--privileged-executor-status",
        "--default-start-plan",
        "--default-start --confirm",
        "--runtime-session-status",
        "--runtime-nft-state",
        "--runtime-logs",
        "--default-stop-plan",
        "--default-stop --confirm",
        "HYPERPATCH ACCEPTANCE: PASS",
        "READY_FOR_USE_WITHIN_P03",
    )
    for fragment in required_fragments:
        assert fragment in text, fragment
    assert "RUNTIME_CLEANUP_NEEDED=1" in text
    assert "best_effort_stop" in text
    assert "trap on_exit EXIT" in text


def test_p03_acceptance_requires_running_and_post_stop_evidence() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    for evidence in (
        "^Default workflow start: started$",
        "^session result: running$",
        "^owner rules result: applied$",
        "^Runtime session status: running$",
        "^owner-rules state: applied$",
        "^Default workflow stop: stopped$",
        "^owner rules result: reverted$",
        "^Default workflow status: stopped$",
        "^nfqws2 session state: stopped$",
    ):
        assert evidence in text
