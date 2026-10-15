import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_board_json_is_consistent() -> None:
    result = subprocess.run(
        [sys.executable, "-B", "tools/gui_checks/check_board.py"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_vendored_devctl_removed() -> None:
    assert not (ROOT / "meta_tools/devctl").exists()
    assert (ROOT / "docs/developer/devctl.md").exists()
