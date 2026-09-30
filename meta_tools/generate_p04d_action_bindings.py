#!/usr/bin/env python3
"""Generate/freeze P04d ActionContract compatibility metadata from build_parser()."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
GUI = ROOT / "gui"
if str(GUI) not in sys.path:
    sys.path.insert(0, str(GUI))

from zap2_gui.app import build_parser  # noqa: E402
from zap2_gui.adapters.legacy_cli import LEGACY_SELECTOR_DESTS, STATIC_MIGRATED_SELECTOR_MAP  # noqa: E402

OUTPUT = ROOT / "gui" / "zap2_gui" / "models" / "action_bindings_generated.py"

ID_OVERRIDES = {
    "gui": "gui.launch",
    "security_blocklist_enable_inbound": "security.blocklist.enable-inbound",
    "security_blocklist_install_timer": "security.blocklist.timer.install",
    "security_blocklist_remove_timer": "security.blocklist.timer.remove",
    "discord_verification_template": "discord.verification.template.create",
    "tunnel_connection_import_vless": "tunnel.connection.vless.import",
    "tunnel_connections": "tunnel.connection.list",
    "tunnel_select_connection": "tunnel.connection.select",
    "discord_launch_through_socks": "discord.socks.launch",
    "discord_stop_launched": "discord.socks.stop",
    "runtime_prepare": "runtime.plan.prepare",
    "runtime_confirm": "runtime.plan.confirm",
    "runtime_migrate_state": "runtime.state.migrate",
    "gui_privileged_command": "gui.privileged-command.show",
    "blockcheck_export_strategies": "blockcheck.strategy.export",
    "blockcheck_validate_strategy_plan": "blockcheck.strategy-validation.plan",
    "select_preset": "preset.select",
    "select_strategy": "strategy.select",
    "list_presets": "preset.list",
    "show_preset": "preset.show",
    "show_preset_profile": "preset.traffic-profile.show",
    "list_profiles": "runtime-context.list",
    "show_profile": "runtime-context.show",
    "list_strategies": "strategy.list",
    "show_strategy": "strategy.show",
}

EFFECT_OVERRIDES = {
    "gui": "launch",
    "security_blocklist_apply": "apply",
    "security_blocklist_disable": "revert",
    "security_blocklist_remove_timer": "revert",
    "discord_verification_template": "prepare",
    "tunnel_connection_import_vless": "import",
    "tunnel_select_connection": "apply",
    "runtime_prepare": "prepare",
    "runtime_confirm": "confirm",
    "runtime_migrate_state": "apply",
    "gui_privileged_command": "show",
    "blockcheck_build": "apply",
    "blockcheck_export_strategies": "export",
    "select_preset": "apply",
    "select_strategy": "apply",
    "service_apply": "apply",
}


def _action_id(selector: str) -> str | None:
    if selector in STATIC_MIGRATED_SELECTOR_MAP:
        return STATIC_MIGRATED_SELECTOR_MAP[selector]
    if selector == "runtime_plan":
        return None
    if selector in ID_OVERRIDES:
        return ID_OVERRIDES[selector]
    parts = selector.split("_")
    if parts[0] in {"list", "show", "select"} and len(parts) > 1:
        verb, noun = parts[0], parts[1:]
        if verb == "list" and noun[-1].endswith("s") and noun[-1] != "status":
            noun[-1] = noun[-1][:-1]
        return ".".join((*noun, verb))
    return ".".join(parts)


def _effect(selector: str) -> str:
    if selector in EFFECT_OVERRIDES:
        return EFFECT_OVERRIDES[selector]
    if selector.startswith("list_"):
        return "list"
    if selector.startswith("show_"):
        return "show"
    if "validate" in selector:
        return "validate"
    if selector.endswith(("_status", "_report", "_last_log")) or selector in {"tunnel_connections", "discord_voice_profiles"}:
        return "show"
    if selector.endswith("_plan") or "_plan_" in selector or selector == "build_plan":
        return "plan"
    if any(word in selector for word in ("preflight", "audit", "diagnose", "analyze", "coverage", "tournament")) or selector.endswith("_check"):
        return "inspect"
    if "import" in selector:
        return "import"
    if "export" in selector:
        return "export"
    if "confirm" in selector:
        return "confirm"
    if "reconcile" in selector:
        return "reconcile"
    if selector.endswith("_start"):
        return "start"
    if selector.endswith("_stop"):
        return "stop"
    if "launch" in selector:
        return "launch"
    if any(word in selector for word in ("probe", "watch", "guided_run")) or selector.endswith(("_run", "_run_row")):
        return "probe"
    if any(word in selector for word in ("enable", "disable", "update", "refresh", "install", "remove", "migrate", "select_", "apply")) or selector.endswith("_build"):
        return "apply"
    return "show"


def _privilege(selector: str, action: argparse.Action, effect: str) -> str:
    help_text = (action.help or "").lower()
    if ("root" in help_text or "sudo" in help_text) and effect not in {"plan", "show", "inspect", "validate", "list", "prepare"}:
        return "bounded-root"
    if effect in {"apply", "revert", "start", "stop", "launch", "import", "export", "confirm"}:
        return "owner"
    return "none"


def _arity(action: argparse.Action) -> int:
    if action.nargs == 0:
        return 0
    if action.nargs is None:
        return 1
    if isinstance(action.nargs, int):
        return action.nargs
    raise RuntimeError(f"unsupported selector nargs for {action.dest}: {action.nargs!r}")


def render() -> str:
    parser = build_parser()
    by_dest = {action.dest: action for action in parser._actions}
    rows: list[dict[str, object]] = []
    for selector in LEGACY_SELECTOR_DESTS:
        if selector == "runtime_plan" or selector in STATIC_MIGRATED_SELECTOR_MAP:
            continue
        action = by_dest[selector]
        action_id = _action_id(selector)
        assert action_id is not None
        effect = _effect(selector)
        rows.append(
            {
                "selector": selector,
                "action_id": action_id,
                "label": (action.help or selector).split(";")[0].strip(),
                "effect": effect,
                "short_help": (action.help or selector).strip(),
                "handler_id": action_id,
                "operand_arity": _arity(action),
                "choices": tuple(str(value) for value in action.choices) if action.choices else (),
                "option_strings": tuple(action.option_strings),
                "privilege": _privilege(selector, action, effect),
            }
        )
    ids = [str(row["action_id"]) for row in rows]
    if len(rows) != 91 or len(ids) != len(set(ids)):
        raise RuntimeError(f"expected 91 unique generated bindings, got rows={len(rows)} unique={len(set(ids))}")
    lines = [
        '"""Generated P04d compatibility bindings for the post-P04c flat CLI.',
        "",
        "Generated from ``build_parser()`` during P04d; runtime code treats this file as frozen metadata,",
        "not as an executable parser authority. Regenerate only with the P04d metadata generator/checker.",
        '"""',
        "from __future__ import annotations",
        "",
        "GENERATED_LEGACY_ACTION_SPECS: tuple[dict[str, object], ...] = (",
    ]
    keys = ("selector", "action_id", "label", "effect", "short_help", "handler_id", "operand_arity", "choices", "option_strings", "privilege")
    for row in rows:
        lines.append("    {")
        for key in keys:
            lines.append(f"        {key!r}: {row[key]!r},")
        lines.append("    },")
    lines.append(")")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    rendered = render()
    if args.check:
        if not OUTPUT.exists() or OUTPUT.read_text(encoding="utf-8") != rendered:
            print(f"P04d generated action metadata drift: {OUTPUT}", file=sys.stderr)
            return 1
        print("P04d generated action metadata: PASS")
        return 0
    OUTPUT.write_text(rendered, encoding="utf-8")
    print(OUTPUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
