#!/usr/bin/env python3
"""Read-only проверка runtime lifecycle contracts Stage 8."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUI_PATH = ROOT / "gui"
if str(GUI_PATH) not in sys.path:
    sys.path.insert(0, str(GUI_PATH))

from zap2_gui.adapters.runtime_contracts import (  # noqa: E402
    runtime_contracts_to_text,
    validate_runtime_contract_catalog,
)


def main() -> int:
    issues = validate_runtime_contract_catalog(ROOT)
    errors = [issue.message for issue in issues if issue.severity == "error"]
    print(runtime_contracts_to_text(ROOT))
    if errors:
        print("Ошибки runtime lifecycle contracts:")
        for error in errors:
            print(f" - {error}")
        return 1
    print("Runtime lifecycle contracts Stage 8 OK; execution disabled")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
