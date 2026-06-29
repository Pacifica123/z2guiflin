"""Small, stable classifier for GUI launch/start failures.

The classifier is intentionally simple: it turns noisy command output into a
short code and a human readable message suitable for an Overview banner.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LaunchIssue:
    code: str
    severity: str
    message: str
    details: str

    def short_text(self) -> str:
        return f"{self.code}: {self.message}"

    def full_text(self) -> str:
        return "\n".join(
            [
                f"code: {self.code}",
                f"severity: {self.severity}",
                f"message: {self.message}",
                "details:",
                self.details.strip() or "нет деталей",
            ]
        )


def classify_launch_issue(
    *,
    action: str,
    text: str = "",
    error: str = "",
    selected_status: str = "",
    all_selected_running: bool | None = None,
) -> LaunchIssue | None:
    """Classify launch/start output into a compact GUI issue code.

    The function does not parse secrets and does not need project state. The
    caller supplies the already-redacted action output and selected-component
    status summary.
    """

    combined = "\n".join(part for part in (action, text, error, selected_status) if part)
    lower = combined.lower()
    details = combined.strip()

    if "nfqws2 binary отсутств" in lower or "needs nfqws2 build" in lower or "nfqws2 not executable" in lower:
        return LaunchIssue(
            code="Z2-ZAPRET-BINARY-MISSING",
            severity="warning",
            message="Zapret не запущен: nfqws2 не собран или не executable.",
            details=details,
        )
    if "unknown transport protocol: xhttp" in lower:
        return LaunchIssue(
            code="Z2-TUNNEL-XHTTP-CORE",
            severity="warning",
            message="VLESS profile использует xhttp, а выбранный core его не принял.",
            details=details,
        )
    if "discord tunnel start: blocked" in lower and ("xhttp" in lower or "splithttp" in lower):
        return LaunchIssue(
            code="Z2-TUNNEL-CORE-INCOMPATIBLE",
            severity="warning",
            message="Выбранный tunnel core несовместим с transport этого VLESS profile.",
            details=details,
        )
    if "needs core binary" in lower or "core binary missing" in lower or "core binary отсутств" in lower:
        return LaunchIssue(
            code="Z2-TUNNEL-CORE-MISSING",
            severity="warning",
            message="Для VLESS tunnel не выбран рабочий core binary.",
            details=details,
        )
    if "needs vless profile" in lower or "active connection: none" in lower or "tunnel connection не найден" in lower:
        return LaunchIssue(
            code="Z2-TUNNEL-PROFILE-MISSING",
            severity="warning",
            message="VLESS tunnel выбран, но активный VLESS profile не найден.",
            details=details,
        )
    if "tunnel core не running" in lower or "t0_core_failed" in lower:
        return LaunchIssue(
            code="Z2-TUNNEL-NOT-RUNNING",
            severity="warning",
            message="Tunnel core не запущен, поэтому VLESS часть набора не работает.",
            details=details,
        )
    if "upstream preflight не прошёл" in lower or "t1_https_through_socks_failed" in lower:
        return LaunchIssue(
            code="Z2-TUNNEL-UPSTREAM-PREFLIGHT",
            severity="warning",
            message="SOCKS поднялся, но HTTPS через VLESS route не прошёл.",
            details=details,
        )
    if "operation not permitted" in lower and "nft" in lower:
        return LaunchIssue(
            code="Z2-PROBE-NFT-PERMISSION",
            severity="warning",
            message="Проверка не смогла прочитать nft counters без повышенных прав.",
            details=details,
        )
    if "execution disabled in stage 10" in lower and "runtime-default-discord-tunnel-socks-start-plan" in lower:
        return LaunchIssue(
            code="Z2-LAUNCH-PLAN-ONLY",
            severity="info",
            message="План был подтверждён, но сам tunnel core ещё не был запущен.",
            details=details,
        )

    start_like = any(token in lower for token in ("start", "запустить", "combined toggle start", "launch composer start"))
    if start_like and all_selected_running is False:
        return LaunchIssue(
            code="Z2-LAUNCH-PARTIAL",
            severity="warning",
            message="Не все выбранные компоненты стали running после запуска.",
            details=details,
        )
    return None


__all__ = ["LaunchIssue", "classify_launch_issue"]
