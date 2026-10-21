"""Transactional one-click preset replacement for Default runtime."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .gui_privilege import execute_gui_privileged_workflow
from .presets import load_preset_catalog, select_preset
from .runtime_default import default_workflow_status, prepare_default_workflow_plan
from .runtime_state import confirm_runtime_plan


@dataclass(frozen=True)
class PresetHotSwapResult:
    requested_preset_id: str
    previous_preset_id: str
    selected_preset_id: str
    runtime_was_running: bool
    state: str
    message: str
    stop_output: str = ""
    start_output: str = ""
    rollback_output: str = ""

    @property
    def success(self) -> bool:
        return self.state in {"selected", "switched"}

    def to_text(self) -> str:
        lines = [
            "Preset hot-swap",
            f"state: {self.state}",
            f"previous: {self.previous_preset_id}",
            f"requested: {self.requested_preset_id}",
            f"selected: {self.selected_preset_id}",
            f"runtime was running: {'yes' if self.runtime_was_running else 'no'}",
            f"message: {self.message}",
        ]
        for name, value in (("stop", self.stop_output), ("start", self.start_output), ("rollback", self.rollback_output)):
            if value:
                lines += ["", name + ":", value.rstrip()]
        return "\n".join(lines)


def _run(root: Path | None, action: str, profile_id: str) -> tuple[bool, str]:
    plan = prepare_default_workflow_plan(root=root, action=action, profile_id=profile_id)
    confirm_runtime_plan(root=root, plan_id=plan.plan_id)
    result = execute_gui_privileged_workflow(
        root=root,
        action=action,
        profile_id=profile_id,
        confirm_plan_id=plan.plan_id,
    )
    return result.ok, result.to_text()


def _restore_previous(root: Path | None, profile_id: str, previous: str, reason: str) -> tuple[bool, str]:
    """Restore selection and make a best-effort restart of the previous runtime."""

    output: list[str] = []
    try:
        select_preset(previous, root=root, workspace_id=profile_id, reason=reason + "-rollback")
    except Exception as exc:
        return False, f"selection rollback error: {exc}"
    try:
        ok, text = _run(root, "start", profile_id)
        output.append(text)
        ok = ok and default_workflow_status(root=root, profile_id=profile_id).session_status.state == "running"
        return ok, "\n".join(output)
    except Exception as exc:
        output.append(f"runtime rollback error: {exc}")
        return False, "\n".join(output)


def hot_swap_preset(
    preset_id: str,
    root: Path | None = None,
    profile_id: str = "default",
    reason: str = "gui-one-click-preset-hot-swap",
) -> PresetHotSwapResult:
    catalog = load_preset_catalog(root)
    if preset_id not in catalog.by_id():
        raise ValueError(f"Неизвестный пресет: {preset_id}")
    previous = catalog.selected_preset_id
    status = default_workflow_status(root=root, profile_id=profile_id)
    running = status.session_status.state == "running"
    if preset_id == previous:
        return PresetHotSwapResult(preset_id, previous, previous, running, "selected", "Пресет уже выбран; runtime не менялся.")
    if not running:
        select_preset(preset_id, root=root, workspace_id=profile_id, reason=reason)
        return PresetHotSwapResult(preset_id, previous, preset_id, False, "selected", "Selection изменён; Default был выключен.")

    try:
        stop_ok, stop_text = _run(root, "stop", profile_id)
    except Exception as exc:
        return PresetHotSwapResult(
            preset_id, previous, previous, True, "stop-failed",
            f"Остановка старого runtime завершилась ошибкой; selection не изменён: {exc}",
            stop_output=str(exc),
        )
    after = default_workflow_status(root=root, profile_id=profile_id)
    if not stop_ok or after.session_status.state == "running":
        return PresetHotSwapResult(preset_id, previous, previous, True, "stop-failed", "Старый runtime не остановлен; selection не изменён.", stop_output=stop_text)

    try:
        select_preset(preset_id, root=root, workspace_id=profile_id, reason=reason)
        start_ok, start_text = _run(root, "start", profile_id)
        after = default_workflow_status(root=root, profile_id=profile_id)
        if start_ok and after.session_status.state == "running":
            return PresetHotSwapResult(preset_id, previous, preset_id, True, "switched", "Default перезапущен с новым пресетом.", stop_output=stop_text, start_output=start_text)
        start_failure = "new runtime returned unsuccessful status"
    except Exception as exc:
        start_ok = False
        start_text = f"start error: {exc}"
        start_failure = str(exc)

    rollback_ok, rollback_text = _restore_previous(root, profile_id, previous, reason)
    state = "start-failed-rolled-back" if rollback_ok else "start-failed-rollback-failed"
    message = (
        "Новый пресет не запустился; предыдущий runtime восстановлен."
        if rollback_ok
        else "Новый пресет не запустился; selection восстановлен, restart старого тоже не удался."
    )
    if start_failure:
        message += f" Причина нового start: {start_failure}."
    return PresetHotSwapResult(preset_id, previous, previous, True, state, message, stop_text, start_text, rollback_text)


def restart_running_preset(root: Path | None = None, profile_id: str = "default") -> tuple[bool, str]:
    """Перезапустить Default с тем же пресетом, чтобы вступили в силу изменения плана.

    Если Default не запущен, ничего не делает: изменения подхватит следующий запуск.
    """

    status = default_workflow_status(root=root, profile_id=profile_id)
    if status.session_status.state != "running":
        return True, "Default не запущен — изменения вступят в силу при следующем запуске."
    stop_ok, stop_text = _run(root, "stop", profile_id)
    if not stop_ok or default_workflow_status(root=root, profile_id=profile_id).session_status.state == "running":
        return False, "Остановить Default не удалось; изменения вступят в силу после перезапуска.\n" + stop_text
    start_ok, start_text = _run(root, "start", profile_id)
    running = default_workflow_status(root=root, profile_id=profile_id).session_status.state == "running"
    if start_ok and running:
        return True, "Default перезапущен с изменениями.\n" + start_text
    return False, "Default остановлен, но не запустился снова — проверьте план на странице «Запуск».\n" + start_text
