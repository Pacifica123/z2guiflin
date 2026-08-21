"""Thin GUI adapter around the standalone tools/discord_machine_diagnostics.py probe."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..project_paths import discover_layout


def discord_machine_diagnostics_tool(root: Path | None = None) -> Path:
    return discover_layout(root).tools_dir / "discord_machine_diagnostics.py"


def discord_machine_diagnostics_command(
    root: Path | None = None,
    *,
    python_executable: str = "python",
    timeout_seconds: float = 4.0,
) -> tuple[str, ...]:
    tool = discord_machine_diagnostics_tool(root)
    return (
        python_executable,
        str(tool),
        "--json",
        "--timeout",
        str(max(1.0, min(15.0, float(timeout_seconds)))),
    )


def parse_discord_machine_diagnostics_json(text: str) -> dict[str, Any]:
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError("Discord diagnostics output must be a JSON object")
    if payload.get("tool") != "discord_machine_diagnostics":
        raise ValueError("Unexpected Discord diagnostics tool identifier")
    if int(payload.get("schemaVersion", 0)) != 1:
        raise ValueError("Unsupported Discord diagnostics schemaVersion")
    return payload


def discord_machine_summary_text(payload: dict[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    title = str(summary.get("title", "Диагностика завершена"))
    detail = str(summary.get("detail", "")).strip()
    actions = summary.get("actions") if isinstance(summary.get("actions"), list) else []
    lines = [title]
    if detail:
        lines.extend(["", detail])
    if actions:
        lines.extend(["", "Что попробовать:"])
        lines.extend(f"• {str(action)}" for action in actions[:8])
    return "\n".join(lines)
