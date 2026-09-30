from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "meta_tools/hyperpatch_acceptance.sh"
RECOVERY = ROOT / "meta_tools/recover_runtime_workspace.py"


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
        "prepare_legacy_v04_migration.py",
        "Legacy v0.4 nft collision guard",
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
    assert "collect_runtime_evidence" in text
    assert "pack_evidence" in text
    assert "evidence archive:" in text
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


def test_p03_acceptance_supports_explicit_previous_workspace_recovery() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "--recover-root" in text
    assert "recover_runtime_workspace.py" in text
    recovery = RECOVERY.read_text(encoding="utf-8")
    assert "prepare_default_workflow_plan" in recovery
    assert "confirm_runtime_plan" in recovery
    assert "execute_bounded_default_workflow" in recovery
    assert "privileged_executor_status" in recovery
    assert "backfill_bounded_drop_identity" in recovery
    assert "os.kill(" not in recovery
    result = subprocess.run(["python", "-m", "py_compile", str(RECOVERY)], text=True, capture_output=True, check=False)
    assert result.returncode == 0, result.stderr


def test_p03d_acceptance_is_arch_portable_and_recovery_is_host_local() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "--no-host-setup" in text
    assert "python-pyqt6" in text
    assert "base-devel pkgconf zlib libnetfilter_queue libnfnetlink libmnl luajit" in text
    assert "Install/update bounded privileged executor" in text
    assert '[[ "${HELPER_STATE}" == "missing" || "${HELPER_STATE}" == "mismatch" ]]' in text
    assert "untrusted/unknown helper не исправляется автоматически" in text
    assert "путь отсутствует на этом host" in text
    assert "ZAP2_UTS_PYTHON=\"${PYTHON_BIN}\"" in text
    assert "ZAP2_PYTHON=\"${PYTHON_BIN}\"" in text


def test_shared_python_selector_prefers_distro_python_before_path_shims() -> None:
    selector = (ROOT / "meta_tools/python_runtime.sh").read_text(encoding="utf-8")
    assert 'candidates+=("${project_root}/.venv/bin/python")' in selector
    assert 'candidates+=("/usr/bin/python3" "/usr/bin/python")' in selector
    assert 'command -v python3' in selector
    assert selector.index('"/usr/bin/python3"') < selector.index('command -v python3')
    assert "ZAP2_PYTHON" in selector
    result = subprocess.run(["bash", "-n", str(ROOT / "meta_tools/python_runtime.sh")], text=True, capture_output=True, check=False)
    assert result.returncode == 0, result.stderr


def test_run_sh_uses_shared_python_selector_for_gui_and_cli() -> None:
    text = (ROOT / "run.sh").read_text(encoding="utf-8")
    assert 'source "$ROOT_DIR/meta_tools/python_runtime.sh"' in text
    assert 'zap2_pick_python "$ROOT_DIR" PyQt6' in text
    assert 'zap2_pick_python "$ROOT_DIR"' in text
    assert "ZAP2_PYTHON=/path/to/python" in text


def test_python_selector_ignores_path_shim_when_distro_python_is_available(tmp_path: Path) -> None:
    distro = Path("/usr/bin/python3")
    if not distro.is_file():
        return
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake = fake_bin / "python3"
    fake.write_text("#!/bin/sh\nexit 91\n", encoding="utf-8")
    fake.chmod(0o755)
    project = tmp_path / "project"
    project.mkdir()
    selector = ROOT / "meta_tools/python_runtime.sh"
    command = f'source "{selector}"; zap2_pick_python "{project}"'
    import os
    env = dict(os.environ)
    env["PATH"] = f"{fake_bin}:{env.get('PATH','')}"
    result = subprocess.run(["bash", "-c", command], text=True, capture_output=True, check=False, env=env)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(distro)


def test_p03e_acceptance_guards_stale_legacy_v04_table_before_start() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert text.index("Legacy v0.4 nft collision guard") < text.index("Default start plan")
    assert "legacy v0.4 nft state не удалось безопасно классифицировать/авторизовать" in text
    helper = (ROOT / "meta_tools/prepare_legacy_v04_migration.py").read_text(encoding="utf-8")
    assert "authorize_stale_legacy_v04_table" in helper
    assert "BoundedNftRunner" in helper


def test_p04a_acceptance_is_read_only_orchestrated_and_archives_evidence() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "--p04a" in text
    assert 'READINESS_MARKER="READY_FOR_USE_WITHIN_P04A"' in text
    assert "check_p04a_re_forensics.py" in text
    assert 'zap2_pick_python "${PROJECT_ROOT}" pytest' in text
    assert "check_p04a_regression.py" in text
    assert "P03 generation identity preserved" in text
    assert "Full deterministic regression" in text
    p04_start = text.index('if [[ "${HYPERPATCH}" == "p04a" ]]; then', text.index('run_step "Host portability fingerprint"'))
    p04_end = text.index("fi", p04_start)
    p04_block = text[p04_start:p04_end]
    assert "sudo" not in p04_block
    assert "--default-start" not in p04_block
    assert "--runtime-apply" not in p04_block
    assert "nft" not in p04_block.lower()
    assert "FINAL_PASS=1" in p04_block


def test_p04b_acceptance_is_read_only_orchestrated_and_archives_evidence() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "--p04b" in text
    assert 'READINESS_MARKER="READY_FOR_USE_WITHIN_P04B"' in text
    assert "check_p04b_execution_plan.py" in text
    assert "check_p04b_regression.py" in text
    assert "P04b immutable execution Plan" in text
    assert "P03 generation identity preserved" in text
    start = text.rindex('\nif [[ "${HYPERPATCH}" == "p04b" ]]; then') + 1
    end = text.index("\nfi", start)
    block = text[start:end]
    assert "sudo" not in block
    assert "--default-start" not in block
    assert "--runtime-apply" not in block
    assert "nft" not in block.lower()
    assert "FINAL_PASS=1" in block


def test_p04c_acceptance_is_read_only_orchestrated_and_archives_evidence() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "--p04c" in text
    assert 'READINESS_MARKER="READY_FOR_USE_WITHIN_P04C"' in text
    assert "check_p04c_action_dispatcher.py" in text
    assert "check_p04c_regression.py" in text
    assert "P04c ActionContract dispatcher" in text
    assert "P03 generation identity preserved" in text
    start = text.rindex('\nif [[ "${HYPERPATCH}" == "p04c" ]]; then') + 1
    end = text.index("\nfi", start)
    block = text[start:end]
    assert "sudo" not in block
    assert "--default-start" not in block
    assert "--runtime-apply" not in block
    assert "nft" not in block.lower()
    assert "FINAL_PASS=1" in block


def test_p04d_acceptance_is_read_only_orchestrated_and_archives_evidence() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "--p04d" in text
    assert 'READINESS_MARKER="READY_FOR_USE_WITHIN_P04D"' in text
    assert "check_p04d_action_contracts.py" in text
    assert "generate_p04d_action_bindings.py --check" in text
    assert "check_p04d_regression.py" in text
    assert "P04d/RC4" in text
    assert "P03 generation identity preserved" in text
    start = text.rindex('\nif [[ "${HYPERPATCH}" == "p04d" ]]; then') + 1
    end = text.index("\nfi", start)
    block = text[start:end]
    assert "sudo" not in block
    assert "--default-start" not in block
    assert "--runtime-apply" not in block
    assert "nft" not in block.lower()
    assert "FINAL_PASS=1" in block


def test_v08_release_acceptance_profile_prepares_p05_without_network_mutation() -> None:
    text = (ROOT / "meta_tools/hyperpatch_acceptance.sh").read_text(encoding="utf-8")
    assert "--v08-release" in text
    assert 'READINESS_MARKER="READY_FOR_P05"' in text
    assert "v0.8 release / P05 handoff" in text
    block = text[text.index('if [[ "${HYPERPATCH}" == "v08-release" ]]'):text.index('if [[ -n "${RECOVER_ROOT}" ]]')]
    assert "check_v08_release.py" in block
    assert "generate_p04d_action_bindings.py --check" in block
    assert "check_p03_core_generation.py" in block
    assert "check_project_tree.py" in block
    assert "check_p04d_regression.py" in block
    assert "sudo" not in block
    assert "FINAL_PASS=1" in block
