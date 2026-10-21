"""Обновление установленного пакета из checkout репозитория.

Пакет z2guiflin собирается из checkout (``meta_tools/build_local_package.sh``),
поэтому «есть обновление» означает одно из двух:

* checkout отстаёт от ``origin/main`` (новые коммиты в репозитории на GitHub);
* содержимое checkout отличается от установленного пакета (другой releaseDigest).

Обновление идёт по шагам, каждый виден пользователю: остановить owned runtime →
``git pull --ff-only`` → собрать archive/PKGBUILD → ``makepkg`` (без root) →
``pkexec pacman -U`` (пароль спрашивает система). Остановка runtime перед установкой —
то, что не даёт новому пакету упасть с «stop/reconcile owned runtime before workspace upgrade».

Сеть трогает только ``git fetch``; команды вызываются списком аргументов, без shell.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Callable, Sequence

from ..distribution import INSTALL_ROOT_ENV, active_runtime_records, user_workspace

Runner = Callable[[Sequence[str], Path | None, int], "CommandResult"]
REMOTE = "origin"
BRANCH = "main"
GIT_TIMEOUT_S = 60
BUILD_TIMEOUT_S = 900


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str = ""


def run_command(argv: Sequence[str], cwd: Path | None = None, timeout: int = GIT_TIMEOUT_S) -> CommandResult:
    try:
        proc = subprocess.run(list(argv), cwd=cwd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        return CommandResult(127, "", f"{argv[0]}: не найден")
    except subprocess.TimeoutExpired:
        return CommandResult(124, "", f"{argv[0]}: превышено время ожидания {timeout} с")
    return CommandResult(proc.returncode, proc.stdout, proc.stderr)


@dataclass
class UpdateStatus:
    checkout: Path | None
    installed_version: str | None = None
    installed_digest: str | None = None
    checkout_version: str | None = None
    checkout_digest: str | None = None
    behind: int = 0
    new_commits: list[str] = field(default_factory=list)
    dirty: bool = False
    branch: str | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def content_differs(self) -> bool:
        return bool(self.installed_digest and self.checkout_digest and self.installed_digest != self.checkout_digest)

    @property
    def available(self) -> bool:
        return self.behind > 0 or self.content_differs

    def to_text(self) -> str:
        lines = ["Обновление z2guiflin"]
        lines.append(f"установлено: {self.installed_version or 'не из пакета (запуск из checkout)'}")
        lines.append(f"checkout: {self.checkout or 'не задан'}" + (f" (версия {self.checkout_version})" if self.checkout_version else ""))
        if self.behind:
            lines.append(f"в репозитории новых коммитов: {self.behind}")
            lines += [f"  {line}" for line in self.new_commits]
        if self.content_differs:
            lines.append("checkout отличается от установленного пакета — пакет можно пересобрать")
        if self.dirty:
            lines.append("в checkout есть незакоммиченные изменения: git pull пропускается")
        if self.branch and self.branch != BRANCH:
            lines.append(f"checkout на ветке {self.branch}, а не {BRANCH}: git pull пропускается")
        lines += [f"! {error}" for error in self.errors]
        lines.append("итог: " + ("доступно обновление" if self.available else "обновлений нет"))
        return "\n".join(lines)


def installed_manifest(environ: dict[str, str] | None = None) -> dict | None:
    env = os.environ if environ is None else environ
    root = env.get(INSTALL_ROOT_ENV)
    if not root:
        return None
    try:
        return json.loads((Path(root) / "RELEASE_MANIFEST.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def checkout_release_digest(checkout: Path) -> tuple[str, str]:
    """(version, releaseDigest) того пакета, который соберётся из checkout сейчас.

    Повторяет packaging/build_release.py без импорта кода из checkout.
    """

    version_match = re.search(r'^version\s*=\s*"([^"]+)"', (checkout / "pyproject.toml").read_text(encoding="utf-8"), re.M)
    if not version_match:
        raise ValueError("в pyproject.toml checkout нет version")
    names = json.loads((checkout / "packaging/release-files.json").read_text(encoding="utf-8"))["files"]
    records = {}
    for name in sorted(names):
        path = checkout / name
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"в checkout нет файла пакета: {name}")
        mode = 0o755 if path.suffix == ".sh" or path.name == "zap2-runtime-executor" else 0o644
        records[name] = {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "mode": mode}
    digest = hashlib.sha256(json.dumps(records, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return version_match.group(1), digest


def is_checkout(path: Path | None) -> bool:
    return bool(path) and (path / ".git").exists() and (path / "meta_tools/build_local_package.sh").is_file()


def check_update(checkout: Path | None, *, fetch: bool = True, runner: Runner = run_command,
                 environ: dict[str, str] | None = None) -> UpdateStatus:
    status = UpdateStatus(checkout=checkout)
    manifest = installed_manifest(environ)
    if manifest:
        status.installed_version = str(manifest.get("version"))
        status.installed_digest = str(manifest.get("releaseDigest"))
    if not is_checkout(checkout):
        status.errors.append("укажите каталог checkout z2guiflin (там, где .git и meta_tools/build_local_package.sh)")
        return status
    assert checkout is not None
    try:
        status.checkout_version, status.checkout_digest = checkout_release_digest(checkout)
    except (OSError, ValueError, KeyError) as exc:
        status.errors.append(f"не удалось посчитать состав пакета из checkout: {exc}")
    branch = runner(["git", "-C", str(checkout), "rev-parse", "--abbrev-ref", "HEAD"], None, GIT_TIMEOUT_S)
    status.branch = branch.stdout.strip() or None
    dirty = runner(["git", "-C", str(checkout), "status", "--porcelain", "--untracked-files=no"], None, GIT_TIMEOUT_S)
    status.dirty = bool(dirty.stdout.strip())
    if fetch:
        fetched = runner(["git", "-C", str(checkout), "fetch", "--quiet", REMOTE, BRANCH], None, GIT_TIMEOUT_S)
        if fetched.returncode != 0:
            status.errors.append("git fetch не удался (нет сети или доступа к репозиторию): " + (fetched.stderr.strip() or str(fetched.returncode)))
    count = runner(["git", "-C", str(checkout), "rev-list", "--count", f"HEAD..{REMOTE}/{BRANCH}"], None, GIT_TIMEOUT_S)
    try:
        status.behind = int(count.stdout.strip() or 0) if count.returncode == 0 else 0
    except ValueError:
        status.behind = 0
    if status.behind:
        log = runner(["git", "-C", str(checkout), "log", "--oneline", "-n", "20", f"HEAD..{REMOTE}/{BRANCH}"], None, GIT_TIMEOUT_S)
        status.new_commits = [line for line in log.stdout.splitlines() if line.strip()]
    return status


@dataclass(frozen=True)
class UpdateStep:
    key: str
    title: str


UPDATE_STEPS = (
    UpdateStep("stop", "Остановить запущенное (zapret, туннель)"),
    UpdateStep("pull", "Забрать новые коммиты (git pull --ff-only)"),
    UpdateStep("build", "Собрать archive и PKGBUILD"),
    UpdateStep("makepkg", "Собрать пакет (makepkg, без root)"),
    UpdateStep("install", "Установить пакет (pkexec pacman -U — пароль спросит система)"),
)


def default_build_dir(version: str) -> Path:
    cache = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    return cache / "zap2gui" / "update" / version


def run_update(
    checkout: Path,
    *,
    log: Callable[[str], None],
    stop_runtime: Callable[[], str],
    runner: Runner = run_command,
    workspace: Path | None = None,
    build_dir: Path | None = None,
) -> bool:
    """Выполняет шаги обновления по порядку; первая ошибка останавливает остальные."""

    def fail(message: str) -> bool:
        log("✗ " + message)
        return False

    if not is_checkout(checkout):
        return fail("каталог не похож на checkout z2guiflin")
    workspace = workspace or user_workspace()

    log("1/5 " + UPDATE_STEPS[0].title)
    if active_runtime_records(workspace):
        log(stop_runtime())
        still = active_runtime_records(workspace)
        if still:
            return fail("runtime не остановился, установка отменена: " + ", ".join(f"{k} ({v})" for k, v in still.items()))
    else:
        log("  ничего не запущено")

    log("2/5 " + UPDATE_STEPS[1].title)
    status = check_update(checkout, fetch=True, runner=runner)
    if status.behind and not status.dirty and status.branch == BRANCH:
        pulled = runner(["git", "-C", str(checkout), "pull", "--ff-only", REMOTE, BRANCH], None, GIT_TIMEOUT_S)
        if pulled.returncode != 0:
            return fail("git pull --ff-only не удался: " + pulled.stderr.strip())
        log("  " + (pulled.stdout.strip().splitlines() or ["готово"])[-1])
    elif status.behind:
        log("  пропущено: " + ("есть незакоммиченные изменения" if status.dirty else f"ветка {status.branch}"))
    else:
        log("  новых коммитов нет")

    version, _digest = checkout_release_digest(checkout)
    out = build_dir or default_build_dir(version)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    log("3/5 " + UPDATE_STEPS[2].title)
    built = runner(["bash", str(checkout / "meta_tools/build_local_package.sh"), "--out", str(out)], checkout, BUILD_TIMEOUT_S)
    if built.returncode != 0:
        return fail("сборка archive/PKGBUILD не удалась: " + (built.stderr.strip() or built.stdout.strip()))

    log("4/5 " + UPDATE_STEPS[3].title)
    made = runner(["makepkg", "-f", "--noconfirm"], out, BUILD_TIMEOUT_S)
    if made.returncode != 0:
        return fail("makepkg не удался: " + (made.stderr.strip() or made.stdout.strip())[-800:])
    packages = sorted(out.glob("zap2gui-linux-*.pkg.tar.*"))
    packages = [p for p in packages if not p.name.endswith(".sig")]
    if not packages:
        return fail("makepkg не оставил пакет в " + str(out))

    log("5/5 " + UPDATE_STEPS[4].title)
    installed = runner(["pkexec", "pacman", "-U", "--noconfirm", str(packages[-1])], out, BUILD_TIMEOUT_S)
    if installed.returncode != 0:
        return fail("установка не удалась или отменена: " + (installed.stderr.strip() or str(installed.returncode)))
    log("✓ пакет установлен. Перезапустите программу, чтобы открыть новую версию.")
    return True


__all__ = [
    "CommandResult", "UpdateStatus", "UPDATE_STEPS", "check_update", "checkout_release_digest",
    "default_build_dir", "installed_manifest", "is_checkout", "run_command", "run_update",
]
