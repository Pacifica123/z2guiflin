"""Оркестрированный профиль поверх upstream Lua-оркестратора ``circular``.

Модуль не реализует собственный перебор стратегий: он только собирает
корректные аргументы nfqws2 для ``circular`` из ``core/zapret2/lua/zapret-auto.lua``
и разбирает его debug-лог. Источник синтаксиса — комментарий над ``function
circular`` и раздел "circular"/"Typical instance invocation scheme" в
``core/zapret2/docs/manual.en.md``:

    --out-range=-s34228
    --in-range=-s5556 --lua-desync=circular[:fails=N:time=S:...]
    --in-range=x
    [--payload=<type>]
    --lua-desync=<func>:<args>:strategy=1
    --lua-desync=<func>:<args>:strategy=2[:final]

``circular`` требует входящие пакеты начала потока (RST, HTTP redirect),
поэтому ``--in-range`` включается только для самого оркестратора и сразу
выключается (``x``) для кандидатов — это затрагивает только данный профиль.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Iterable

CIRCULAR_FUNCTION = "circular"
# Значения из manual.en.md: success detector срабатывает на s4096/s32768,
# плюс один максимальный TCP-пакет 1460 байт запаса.
CIRCULAR_IN_RANGE = "-s5556"
CIRCULAR_OUT_RANGE = "-s34228"

_ALLOWED_PARAMS = ("fails", "time", "nld", "reqhost", "key")
_FLAG_PARAMS = frozenset({"reqhost"})
_INT_PARAMS = frozenset({"fails", "time", "nld"})
_RESERVED_INSTANCE_ARGS = frozenset({"strategy", "final"})
_KEY_RE = re.compile(r"^[A-Za-z0-9_]+$")
_FUNC_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _instance_body(raw: str) -> str:
    value = str(raw).strip()
    if value.startswith("--lua-desync="):
        value = value[len("--lua-desync="):]
    elif value.startswith("--"):
        raise ValueError(
            f"Кандидат оркестратора может содержать только --lua-desync, получено: {value!r}"
        )
    if not value:
        raise ValueError("Пустой lua-desync instance в кандидате оркестратора")
    func, _, rest = value.partition(":")
    if not _FUNC_RE.fullmatch(func):
        raise ValueError(f"Недопустимое имя Lua-функции в кандидате: {func!r}")
    if func == CIRCULAR_FUNCTION:
        raise ValueError("Вложенный circular внутри кандидата не поддерживается")
    for part in rest.split(":") if rest else ():
        name = part.partition("=")[0]
        if name in _RESERVED_INSTANCE_ARGS:
            raise ValueError(
                f"Аргумент {name!r} назначается автоматически; уберите его из кандидата: {value!r}"
            )
    return value


@dataclass(frozen=True)
class OrchestratedProfile:
    """Профиль, где ``circular`` переключает 2..N стратегий-кандидатов.

    ``candidates`` — список стратегий; каждая стратегия — последовательность
    lua-desync instance (``func:arg=v`` или ``--lua-desync=func:arg=v``).
    Теги ``strategy=N`` назначаются автоматически без пропусков.
    """

    candidates: tuple[tuple[str, ...], ...]
    params: dict[str, str | int | bool] = field(default_factory=dict)
    final_last: bool = False
    payload: str = ""

    def validate(self) -> None:
        if len(self.candidates) < 2:
            raise ValueError("Оркестратору нужно минимум 2 стратегии-кандидата")
        for index, candidate in enumerate(self.candidates, start=1):
            if not candidate:
                raise ValueError(f"Стратегия-кандидат {index} пуста (пропуски недопустимы)")
            for item in candidate:
                _instance_body(item)
        for name, value in self.params.items():
            if name not in _ALLOWED_PARAMS:
                raise ValueError(
                    f"Неизвестный параметр circular: {name!r}. Допустимы: {', '.join(_ALLOWED_PARAMS)}"
                )
            if name in _FLAG_PARAMS:
                if not isinstance(value, bool):
                    raise ValueError(f"Параметр {name} — флаг (true/false)")
            elif name in _INT_PARAMS:
                if isinstance(value, bool) or not str(value).isdigit() or int(value) < 1:
                    raise ValueError(f"Параметр {name} должен быть целым числом >= 1, получено {value!r}")
            elif name == "key":
                if not _KEY_RE.fullmatch(str(value)):
                    raise ValueError(f"Параметр key должен состоять из [A-Za-z0-9_], получено {value!r}")
        if self.payload and not re.fullmatch(r"[a-z0-9_,]+", self.payload):
            raise ValueError(f"Недопустимый payload: {self.payload!r}")

    def circular_instance(self) -> str:
        parts = [CIRCULAR_FUNCTION]
        for name in _ALLOWED_PARAMS:
            if name not in self.params:
                continue
            value = self.params[name]
            if name in _FLAG_PARAMS:
                if value:
                    parts.append(name)
            else:
                parts.append(f"{name}={value}")
        return ":".join(parts)

    def to_strategy_args(self) -> tuple[str, ...]:
        """Аргументы уровня профиля (без filter/target) для nfqws2."""

        self.validate()
        # circular стоит ДО --payload: детектору нужны пакеты без payload
        # (входящий RST) и HTTP-ответы; payload-фильтр относится только к
        # кандидатам (как в manual.en.md, "Typical instance invocation scheme").
        args: list[str] = [
            f"--out-range={CIRCULAR_OUT_RANGE}",
            f"--in-range={CIRCULAR_IN_RANGE}",
            f"--lua-desync={self.circular_instance()}",
            "--in-range=x",
        ]
        if self.payload:
            args.append(f"--payload={self.payload}")
        last = len(self.candidates)
        for number, candidate in enumerate(self.candidates, start=1):
            for position, item in enumerate(candidate):
                body = f"{_instance_body(item)}:strategy={number}"
                if self.final_last and number == last and position == 0:
                    body += ":final"
                args.append(f"--lua-desync={body}")
        return tuple(args)


def referenced_lua_functions(args: Iterable[str]) -> tuple[str, ...]:
    names: list[str] = []
    for arg in args:
        if arg.startswith("--lua-desync="):
            name = arg[len("--lua-desync="):].partition(":")[0]
            if name not in names:
                names.append(name)
    return tuple(names)


def candidates_from_args(args: Iterable[str]) -> tuple[str, ...]:
    """Выделить lua-desync instance из готовой стратегии профиля.

    Используется для сборки кандидатов из strategies/*.json и шаблонов
    пресетов. Instance с ``strategy``/``final`` или вложенным circular
    пропускаются — такие стратегии уже оркестрированы.
    """

    result: list[str] = []
    for arg in args:
        if not str(arg).startswith("--lua-desync="):
            continue
        try:
            result.append(_instance_body(arg))
        except ValueError:
            return ()
    return tuple(result)


# --- debug log ---------------------------------------------------------------

_HOST_RE = re.compile(r"automate: host record key 'autostate\.([^.']+)\.([^']+)'")
_CURRENT_RE = re.compile(r"circular: current strategy (\d+)")
_ROTATE_RE = re.compile(r"circular: rotate strategy to (\d+)")
_FINAL_RE = re.compile(r"circular: final strategy (\d+) reached")
_REASONS = (
    ("standard_failure_detector: incoming RST", "rst"),
    ("standard_failure_detector: retransmission", "retransmission"),
    ("looks like DPI redirect", "http_redirect"),
    ("standard_failure_detector: arg.udp_out", "udp_no_reply"),
)


@dataclass(frozen=True)
class CircularSwitch:
    host: str
    from_strategy: int | None
    to_strategy: int
    reason: str
    key: str = ""
    final: bool = False


def parse_circular_log(lines: Iterable[str]) -> tuple[CircularSwitch, ...]:
    """Разобрать debug-лог nfqws2 (--debug) в список переключений circular.

    Хост берётся из последней строки ``automate: host record key``, причина —
    из последней строки failure detector перед ``automate: failure detected``.
    ``from_strategy`` — последняя увиденная ``current strategy`` этого хоста
    (None, если её не было в окне лога).
    """

    switches: list[CircularSwitch] = []
    current: dict[tuple[str, str], int] = {}
    key = host = ""
    reason = "unknown"
    for raw in lines:
        line = str(raw)
        match = _HOST_RE.search(line)
        if match:
            key, host = match.group(1), match.group(2)
            reason = "unknown"
            continue
        for marker, code in _REASONS:
            if marker in line and "NOT a DPI redirect" not in line and "not counting" not in line:
                reason = code
        match = _ROTATE_RE.search(line)
        if match:
            target = int(match.group(1))
            switches.append(
                CircularSwitch(
                    host=host or "?",
                    from_strategy=current.get((key, host)),
                    to_strategy=target,
                    reason=reason,
                    key=key,
                )
            )
            current[(key, host)] = target
            continue
        match = _FINAL_RE.search(line)
        if match and switches and switches[-1].host == (host or "?"):
            last = switches[-1]
            switches[-1] = CircularSwitch(last.host, last.from_strategy, last.to_strategy, last.reason, last.key, True)
            continue
        match = _CURRENT_RE.search(line)
        if match:
            current[(key, host)] = int(match.group(1))
    return tuple(switches)


def circular_switches_to_text(switches: Iterable[CircularSwitch]) -> str:
    rows = []
    for item in switches:
        source = "?" if item.from_strategy is None else str(item.from_strategy)
        suffix = " (final, ротация остановлена)" if item.final else ""
        rows.append(f"{item.host}: стратегия {source} → {item.to_strategy}, причина: {item.reason}{suffix}")
    return "\n".join(rows) if rows else "Переключений circular в логе нет."
