"""GUI launch composer for combining runtime modules.

The composer is deliberately small and explicit: it does not invent a hidden
routing stack. It gives the GUI a stable registry of launchable components,
marks future components as planned, and runs selected supported components in a
known order. Privileged Zapret actions still go through the existing GUI sudo
askpass bridge; VLESS remains a user-space external-core lane.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .discord_tunnel import (
    DEFAULT_CORE_KIND,
    DEFAULT_SOCKS_PORT,
    discord_tunnel_plan_to_text,
    discord_tunnel_start_to_text,
    discord_tunnel_status_to_text,
    discord_tunnel_stop_to_text,
    ensure_tunnel_store,
)
from .gui_runtime_controls import (
    current_default_plan_id,
    gui_confirm_plan,
    gui_default_status,
    gui_prepare_default_start,
    gui_prepare_default_stop,
    gui_privileged_default_start,
    gui_privileged_default_stop,
)
from .runtime_default import default_workflow_status
from .runtime_state import confirm_runtime_plan
from ..project_paths import discover_layout

LAUNCH_COMPOSER_STAGE = "v0.4-alpha_stage7z"
COMPONENT_ZAPRET_DEFAULT = "zapret-default"
COMPONENT_TUNNEL_VLESS = "tunnel-vless"
COMPONENT_SOCKS5 = "socks5"
COMPONENT_MTPROTO = "mtproto"
COMPONENT_CUSTOM = "custom"
SUPPORTED_LAUNCH_COMPONENTS = (COMPONENT_ZAPRET_DEFAULT, COMPONENT_TUNNEL_VLESS)
KNOWN_LAUNCH_COMPONENTS = (
    COMPONENT_ZAPRET_DEFAULT,
    COMPONENT_TUNNEL_VLESS,
    COMPONENT_SOCKS5,
    COMPONENT_MTPROTO,
    COMPONENT_CUSTOM,
)
DEFAULT_SELECTED_COMPONENTS = (COMPONENT_ZAPRET_DEFAULT,)
START_ORDER = (COMPONENT_ZAPRET_DEFAULT, COMPONENT_TUNNEL_VLESS)
STOP_ORDER = (COMPONENT_TUNNEL_VLESS, COMPONENT_ZAPRET_DEFAULT)


@dataclass(frozen=True)
class LaunchComponentSpec:
    component_id: str
    title: str
    category: str
    summary: str
    supported: bool
    requires_sudo: bool
    default_checked: bool = False
    planned_note: str = ""


@dataclass(frozen=True)
class LaunchComponentView:
    spec: LaunchComponentSpec
    selected: bool
    status: str
    ready: str


COMPONENT_SPECS: dict[str, LaunchComponentSpec] = {
    COMPONENT_ZAPRET_DEFAULT: LaunchComponentSpec(
        component_id=COMPONENT_ZAPRET_DEFAULT,
        title="Zapret default",
        category="traffic",
        summary="nfqws2 + owner-rules default workflow через существующий confirmation/sudo-askpass путь.",
        supported=True,
        requires_sudo=True,
        default_checked=True,
    ),
    COMPONENT_TUNNEL_VLESS: LaunchComponentSpec(
        component_id=COMPONENT_TUNNEL_VLESS,
        title="VLESS tunnel",
        category="proxy",
        summary="Внешний xray/v2ray/sing-box core с loopback SOCKS; без sudo и без firewall mutation.",
        supported=True,
        requires_sudo=False,
    ),
    COMPONENT_SOCKS5: LaunchComponentSpec(
        component_id=COMPONENT_SOCKS5,
        title="SOCKS5 upstream",
        category="planned",
        summary="Будущий прямой SOCKS5 upstream без VLESS-config generation.",
        supported=False,
        requires_sudo=False,
        planned_note="planned placeholder; start/stop пока недоступны",
    ),
    COMPONENT_MTPROTO: LaunchComponentSpec(
        component_id=COMPONENT_MTPROTO,
        title="MTProto",
        category="planned",
        summary="Будущий Telegram/MTProto-like lane, если он понадобится как отдельный транспорт.",
        supported=False,
        requires_sudo=False,
        planned_note="planned placeholder; протокол ещё не описан",
    ),
    COMPONENT_CUSTOM: LaunchComponentSpec(
        component_id=COMPONENT_CUSTOM,
        title="Custom module",
        category="planned",
        summary="Заготовка под иной launch adapter без переписывания панели выбора.",
        supported=False,
        requires_sudo=False,
        planned_note="planned placeholder; нужен отдельный adapter contract",
    ),
}


def normalize_launch_components(components: str | Iterable[str] | None) -> tuple[str, ...]:
    """Normalize comma/list component input and keep stable start ordering."""

    if components is None:
        raw = list(DEFAULT_SELECTED_COMPONENTS)
    elif isinstance(components, str):
        raw = [item.strip() for item in components.replace(";", ",").split(",")]
    else:
        raw = [str(item).strip() for item in components]
    selected: list[str] = []
    for item in raw:
        if not item:
            continue
        if item not in KNOWN_LAUNCH_COMPONENTS:
            raise ValueError(f"Unknown launch component: {item}")
        if item not in selected:
            selected.append(item)
    if not selected:
        raise ValueError("Нужно выбрать хотя бы один launch component")
    ordered = [item for item in START_ORDER if item in selected]
    ordered.extend(item for item in KNOWN_LAUNCH_COMPONENTS if item in selected and item not in ordered)
    return tuple(ordered)


def _selected_for_stop(components: str | Iterable[str] | None) -> tuple[str, ...]:
    selected = normalize_launch_components(components)
    return tuple(item for item in STOP_ORDER if item in selected)


def _zapret_state(root: Path | None, profile_id: str) -> str:
    try:
        status = default_workflow_status(root=root, profile_id=profile_id)
        if status.workflow_state == "started" and status.session_status.state == "running":
            return "running"
        if status.workflow_state == "started":
            return f"partial:{status.session_status.state}"
        return "stopped"
    except Exception as exc:  # pragma: no cover - defensive GUI path
        return f"unknown:{exc}"


def _tunnel_state(root: Path | None, profile_id: str) -> str:
    text = discord_tunnel_status_to_text(root=root, profile_id=profile_id)
    if "state: running" in text and "core running: yes" in text:
        return "running"
    if "state: stale" in text:
        return "stale"
    return "stopped"


def _tunnel_ready(root: Path | None, profile_id: str, core_binary: str | None) -> str:
    try:
        paths = ensure_tunnel_store(root)
        active = paths.tunnel_root / f"{profile_id}.active-connection.json"
        has_connection = active.exists()
        if not has_connection:
            # Fall back to status text in case the storage format changes later.
            status = discord_tunnel_status_to_text(root=root, profile_id=profile_id)
            has_connection = "active connection: none" not in status
        if not has_connection:
            return "needs VLESS profile"
        if not (core_binary or ""):
            return "needs core binary path"
        binary = Path(str(core_binary)).expanduser()
        if not binary.is_file():
            return "core binary missing"
        if not bool(binary.stat().st_mode & 0o111):
            return "core binary not executable"
        return "ready"
    except Exception as exc:  # pragma: no cover - defensive GUI path
        return f"unknown:{exc}"


def launch_component_views(
    *,
    components: str | Iterable[str] | None = None,
    profile_id: str = "default",
    core_binary: str | None = None,
    root: Path | None = None,
) -> tuple[LaunchComponentView, ...]:
    """Return categorized GUI rows for all known launch components."""

    discover_layout(root)
    selected = set(normalize_launch_components(components)) if components is not None else set(DEFAULT_SELECTED_COMPONENTS)
    rows: list[LaunchComponentView] = []
    for component_id in KNOWN_LAUNCH_COMPONENTS:
        spec = COMPONENT_SPECS[component_id]
        if component_id == COMPONENT_ZAPRET_DEFAULT:
            status = _zapret_state(root, profile_id)
            ready = "unknown" if status.startswith("unknown") else "ready"
        elif component_id == COMPONENT_TUNNEL_VLESS:
            status = _tunnel_state(root, profile_id)
            ready = _tunnel_ready(root, profile_id, core_binary)
        else:
            status = "planned"
            ready = spec.planned_note
        rows.append(LaunchComponentView(spec=spec, selected=component_id in selected, status=status, ready=ready))
    return tuple(rows)


def _unsupported_selected(selected: Iterable[str]) -> tuple[str, ...]:
    return tuple(item for item in selected if not COMPONENT_SPECS[item].supported)


def _plan_lines_for_selected(selected: tuple[str, ...]) -> list[str]:
    lines: list[str] = []
    for index, component_id in enumerate(selected, start=1):
        spec = COMPONENT_SPECS[component_id]
        sudo = "sudo" if spec.requires_sudo else "user-space"
        lines.append(f"{index}. {component_id} [{spec.category}, {sudo}] — {spec.summary}")
    return lines


def launch_composer_status_to_text(
    *,
    components: str | Iterable[str] | None = None,
    profile_id: str = "default",
    core_binary: str | None = None,
    root: Path | None = None,
) -> str:
    selected = normalize_launch_components(components)
    rows = launch_component_views(components=selected, profile_id=profile_id, core_binary=core_binary, root=root)
    lines = [
        "Launch composer status",
        f"stage: {LAUNCH_COMPOSER_STAGE}",
        f"profile: {profile_id}",
        f"selected: {', '.join(selected)}",
        "",
        "Components:",
    ]
    for row in rows:
        mark = "[x]" if row.selected else "[ ]"
        support = "supported" if row.spec.supported else "planned"
        sudo = "sudo" if row.spec.requires_sudo else "no-sudo"
        lines.append(f"{mark} {row.spec.component_id} :: {row.spec.title} :: {support} :: {sudo} :: state={row.status} :: ready={row.ready}")
    lines.extend(
        [
            "",
            "Safety:",
            "- This status command is read-only.",
            "- Secrets are not printed; tunnel connection details stay redacted in the tunnel adapter.",
        ]
    )
    return "\n".join(lines)


def launch_composer_plan_to_text(
    *,
    components: str | Iterable[str] | None = None,
    profile_id: str = "default",
    core_binary: str | None = None,
    core_kind: str = DEFAULT_CORE_KIND,
    socks_port: int = DEFAULT_SOCKS_PORT,
    root: Path | None = None,
) -> str:
    selected = normalize_launch_components(components)
    unsupported = _unsupported_selected(selected)
    rows = {row.spec.component_id: row for row in launch_component_views(components=selected, profile_id=profile_id, core_binary=core_binary, root=root)}
    lines = [
        "Launch composer plan",
        f"stage: {LAUNCH_COMPOSER_STAGE}",
        f"profile: {profile_id}",
        f"selected: {', '.join(selected)}",
        f"start order: {' -> '.join(selected)}",
        f"stop order: {' -> '.join(_selected_for_stop(selected))}",
        "",
        "Selected components:",
        *_plan_lines_for_selected(selected),
    ]
    if unsupported:
        lines.extend(["", f"blocked: unsupported planned components selected: {', '.join(unsupported)}"])
    if COMPONENT_TUNNEL_VLESS in selected:
        ready = rows[COMPONENT_TUNNEL_VLESS].ready
        lines.extend(
            [
                "",
                "VLESS tunnel inputs:",
                f"- core kind: {core_kind}",
                f"- core binary: {'set' if core_binary else 'not set'}",
                f"- socks port: {socks_port}",
                f"- readiness: {ready}",
                "- route: local SOCKS listener only; client apps must be launched/configured to use it",
            ]
        )
    if COMPONENT_ZAPRET_DEFAULT in selected and COMPONENT_TUNNEL_VLESS in selected:
        lines.extend(
            [
                "",
                "Combination note:",
                "- zapret-default + tunnel-vless is allowed only as an explicit composer experiment.",
                "- Start order keeps Zapret first, then starts the user-space tunnel with an explicit parallel flag.",
                "- Stop order is reversed: tunnel first, then Zapret.",
                "- This still does not transparently route Discord into SOCKS; use the Tunnel tab route controls or --discord-launch-through-socks.",
            ]
        )
    lines.extend(
        [
            "",
            "Execution policy:",
            "- Plan/status commands do not start anything.",
            "- Zapret start/stop still requires owner confirmation and GUI sudo-askpass.",
            "- VLESS start/stop uses only the managed external core PID in .zap2/tunnel/runtime.",
        ]
    )
    return "\n".join(lines)


def launch_composer_start_to_text(
    *,
    components: str | Iterable[str] | None = None,
    profile_id: str = "default",
    core_binary: str | None = None,
    core_kind: str = DEFAULT_CORE_KIND,
    socks_port: int = DEFAULT_SOCKS_PORT,
    root: Path | None = None,
) -> str:
    selected = normalize_launch_components(components)
    unsupported = _unsupported_selected(selected)
    if unsupported:
        raise ValueError(f"Unsupported planned components selected: {', '.join(unsupported)}")
    parts: list[str] = [launch_composer_plan_to_text(components=selected, profile_id=profile_id, core_binary=core_binary, core_kind=core_kind, socks_port=socks_port, root=root)]
    parts.append("\nLaunch composer start")
    for component_id in selected:
        if component_id == COMPONENT_ZAPRET_DEFAULT:
            if _zapret_state(root, profile_id) == "running":
                parts.append("zapret-default: already running; skipped")
                continue
            parts.append("zapret-default: prepare start-plan")
            start_plan = gui_prepare_default_start(root=root, profile_id=profile_id)
            parts.append(start_plan)
            plan_id = current_default_plan_id(root, "start", profile_id)
            parts.append("zapret-default: confirm start-plan")
            parts.append(gui_confirm_plan(root=root, plan_id=plan_id))
            parts.append("zapret-default: execute via GUI sudo-askpass")
            parts.append(gui_privileged_default_start(root=root, profile_id=profile_id, confirm_plan_id=plan_id))
        elif component_id == COMPONENT_TUNNEL_VLESS:
            if _tunnel_state(root, profile_id) == "running":
                parts.append("tunnel-vless: already running; skipped")
                continue
            parts.append("tunnel-vless: prepare start-plan")
            parts.append(discord_tunnel_plan_to_text(root=root, profile_id=profile_id, core_binary=core_binary, core_kind=core_kind, socks_port=socks_port))
            plan_id = f"runtime-{profile_id}-discord-tunnel-socks-start-plan"
            parts.append("tunnel-vless: confirm start-plan")
            parts.append(confirm_runtime_plan(root=root, plan_id=plan_id).to_text())
            parts.append("tunnel-vless: start external core")
            parts.append(discord_tunnel_start_to_text(root=root, profile_id=profile_id, confirm_plan_id=plan_id, allow_parallel_with_zapret=COMPONENT_ZAPRET_DEFAULT in selected))
    parts.append("\nFinal status")
    parts.append(launch_composer_status_to_text(components=selected, profile_id=profile_id, core_binary=core_binary, root=root))
    return "\n\n".join(parts)


def launch_composer_stop_to_text(
    *,
    components: str | Iterable[str] | None = None,
    profile_id: str = "default",
    root: Path | None = None,
) -> str:
    selected = _selected_for_stop(components)
    unsupported = _unsupported_selected(selected)
    if unsupported:
        raise ValueError(f"Unsupported planned components selected: {', '.join(unsupported)}")
    parts: list[str] = [
        "Launch composer stop",
        f"stage: {LAUNCH_COMPOSER_STAGE}",
        f"profile: {profile_id}",
        f"selected stop order: {' -> '.join(selected)}",
    ]
    for component_id in selected:
        if component_id == COMPONENT_TUNNEL_VLESS:
            parts.append("\ntunnel-vless: stop managed external core")
            parts.append(discord_tunnel_stop_to_text(root=root, profile_id=profile_id))
        elif component_id == COMPONENT_ZAPRET_DEFAULT:
            if _zapret_state(root, profile_id) == "stopped":
                parts.append("\nzapret-default: already stopped; skipped")
                continue
            parts.append("\nzapret-default: prepare stop-plan")
            stop_plan = gui_prepare_default_stop(root=root, profile_id=profile_id)
            parts.append(stop_plan)
            plan_id = current_default_plan_id(root, "stop", profile_id)
            parts.append("zapret-default: confirm stop-plan")
            parts.append(gui_confirm_plan(root=root, plan_id=plan_id))
            parts.append("zapret-default: execute via GUI sudo-askpass")
            parts.append(gui_privileged_default_stop(root=root, profile_id=profile_id, confirm_plan_id=plan_id))
    parts.append("\nFinal status")
    parts.append(launch_composer_status_to_text(components=tuple(reversed(selected)), profile_id=profile_id, root=root))
    return "\n\n".join(parts)
