"""Проверка загрузки вложений Discord по слоям: DNS → TCP → TLS → HTTP → объём.

Зачем отдельно от Blockcheck: Blockcheck и ping отвечают на вопрос «открывается ли
соединение», а вложение может открыться и встать на первых килобайтах тела. ping
проверяет только IP по ICMP; DPI работает по TLS (SNI) и по объёму внутри TCP.
Этот probe читает тело и запоминает, на каком байте поток остановился.

Только чтение: обычные HTTPS-запросы от пользователя, без привилегий и без firewall.
Если Default запущен, запросы идут через его стратегию — это и нужно проверить.
"""

from __future__ import annotations

import socket
import ssl
import time
from dataclasses import dataclass, field
from typing import Callable
from urllib.parse import urlsplit

DISCORD_ATTACHMENT_SUFFIXES = ("discordapp.com", "discordapp.net", "discord.com", "discord.media")
CONTROL_URLS = (
    ("media", "https://media.discordapp.net/embed/avatars/0.png"),
    ("cdn", "https://cdn.discordapp.com/embed/avatars/0.png"),
)
MAX_BYTES = 2 * 1024 * 1024
# Ограничение «по объёму» на ТСПУ обрывает поток после ~16–20 КБ; берём запас.
VOLUME_CAP_SUSPECT_BYTES = 48 * 1024


@dataclass
class TransferResult:
    label: str
    url: str
    host: str
    addresses: tuple[str, ...] = ()
    stage: str = ""  # dns | tcp | tls | http | body | ok
    error: str = ""
    status: int | None = None
    content_length: int | None = None
    body_bytes: int = 0
    stalled: bool = False
    timings_ms: dict[str, int] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.stage == "ok"

    def verdict(self) -> str:
        if self.stage == "dns":
            return f"DNS: {self.host} не разрешается ({self.error})"
        if self.stage == "tcp":
            return f"TCP: нет соединения с {self.addresses[0] if self.addresses else self.host}:443 ({self.error}) — похоже на блок по IP"
        if self.stage == "tls":
            if "reset" in self.error.lower() or "eof" in self.error.lower():
                return f"TLS: соединение сброшено на рукопожатии ({self.error}) — DPI видит SNI {self.host} и вставляет сброс"
            return f"TLS: рукопожатие не завершилось ({self.error}) — типичный признак DPI по SNI {self.host}"
        if self.stage == "http":
            return f"HTTP: заголовки ответа не пришли ({self.error})"
        if self.stage == "body":
            kb = self.body_bytes / 1024
            if self.body_bytes and self.body_bytes <= VOLUME_CAP_SUSPECT_BYTES:
                return (
                    f"Тело: поток встал после {kb:.1f} КБ — похоже на ограничение по объёму на пути "
                    "(соединение открыто, данные перестают идти). Blockcheck и ping такого не видят."
                )
            return f"Тело: загрузка встала после {kb:.1f} КБ ({self.error})"
        speed = ""
        body_ms = self.timings_ms.get("body", 0)
        if self.body_bytes and body_ms:
            speed = f", {self.body_bytes / 1024 / (body_ms / 1000):.0f} КБ/с"
        return f"OK: HTTP {self.status}, получено {self.body_bytes / 1024:.1f} КБ{speed}"

    def to_text(self) -> str:
        timings = " ".join(f"{key}={value}мс" for key, value in self.timings_ms.items())
        addr = ", ".join(self.addresses[:2]) or "—"
        return f"[{self.label}] {self.host} ({addr})\n  {self.verdict()}\n  {timings}".rstrip()


def validate_attachment_url(url: str) -> str:
    value = url.strip()
    parts = urlsplit(value)
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" or not host:
        raise ValueError("нужна https-ссылка на вложение (ПКМ по файлу в Discord → «Копировать ссылку»)")
    if not any(host == suffix or host.endswith("." + suffix) for suffix in DISCORD_ATTACHMENT_SUFFIXES):
        raise ValueError(f"{host} не похож на адрес Discord; проверка шлёт запросы только на домены Discord")
    return value


Resolver = Callable[[str], tuple[str, ...]]


def _resolve(host: str) -> tuple[str, ...]:
    infos = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    seen: list[str] = []
    for info in infos:
        address = str(info[4][0])
        if address not in seen:
            seen.append(address)
    return tuple(seen)


def transfer_probe(
    label: str,
    url: str,
    *,
    timeout: float = 6.0,
    stall_seconds: float = 6.0,
    max_bytes: int = MAX_BYTES,
    resolver: Resolver | None = None,
    connect: Callable[..., socket.socket] = socket.create_connection,
) -> TransferResult:
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    path = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
    result = TransferResult(label=label, url=url, host=host)
    started = time.monotonic()

    def mark(name: str) -> None:
        result.timings_ms[name] = round((time.monotonic() - started) * 1000) - sum(result.timings_ms.values())

    try:
        result.addresses = (resolver or _resolve)(host)
    except OSError as exc:
        result.stage, result.error = "dns", str(exc)
        return result
    if not result.addresses:
        result.stage, result.error = "dns", "пустой ответ"
        return result
    mark("dns")
    try:
        raw = connect((result.addresses[0], 443), timeout=timeout)
    except OSError as exc:
        result.stage, result.error = "tcp", str(exc) or type(exc).__name__
        return result
    mark("tcp")
    try:
        context = ssl.create_default_context()
        tls = context.wrap_socket(raw, server_hostname=host)
    except (OSError, ssl.SSLError) as exc:
        raw.close()
        result.stage, result.error = "tls", str(exc) or type(exc).__name__
        return result
    mark("tls")
    with tls:
        request = (
            f"GET {path} HTTP/1.1\r\nHost: {host}\r\nUser-Agent: zap2-gui\r\n"
            f"Range: bytes=0-{max_bytes - 1}\r\nAccept-Encoding: identity\r\nConnection: close\r\n\r\n"
        )
        try:
            tls.sendall(request.encode("ascii"))
            head = b""
            while b"\r\n\r\n" not in head:
                chunk = tls.recv(4096)
                if not chunk:
                    break
                head += chunk
                if len(head) > 65536:
                    break
        except OSError as exc:
            result.stage, result.error = "http", str(exc) or type(exc).__name__
            return result
        header_blob, _, body = head.partition(b"\r\n\r\n")
        lines = header_blob.decode("latin-1", errors="replace").split("\r\n")
        try:
            result.status = int(lines[0].split()[1])
        except (IndexError, ValueError):
            result.stage, result.error = "http", "нет статусной строки"
            return result
        for line in lines[1:]:
            name, _, value = line.partition(":")
            if name.strip().lower() == "content-length" and value.strip().isdigit():
                result.content_length = int(value.strip())
        mark("http")
        received = len(body)
        tls.settimeout(stall_seconds)
        expected = min(result.content_length, max_bytes) if result.content_length is not None else max_bytes
        try:
            while received < expected:
                chunk = tls.recv(65536)
                if not chunk:
                    break
                received += len(chunk)
        except (socket.timeout, TimeoutError):
            result.body_bytes, result.stalled = received, True
            result.stage, result.error = "body", f"нет данных {stall_seconds:.0f} с"
            mark("body")
            return result
        except OSError as exc:
            result.body_bytes = received
            result.stage, result.error = "body", str(exc) or type(exc).__name__
            mark("body")
            return result
        result.body_bytes = received
        mark("body")
        result.stage = "ok"
        return result


def interpret(results: list[TransferResult], attachment_url: str) -> list[str]:
    by_label = {item.label: item for item in results}
    media, cdn, attachment = by_label.get("media"), by_label.get("cdn"), by_label.get("attachment")
    lines: list[str] = []
    if attachment is not None and not attachment.ok and cdn is not None and cdn.ok:
        if attachment.stage == "body":
            lines.append(
                "Соединение с cdn.discordapp.com открывается, а большое тело обрывается: это не устаревший домен, "
                "а ограничение по объёму на пути. Нужна стратегия, которая проходит дальше первых килобайт "
                "(или туннель для cdn.discordapp.com); Blockcheck с CURL_PAD помогает увидеть это при подборе."
            )
        else:
            lines.append("Маленький файл с cdn.discordapp.com проходит, вложение — нет: смотрите стадию выше.")
    if media is not None and cdn is not None and media.ok and not cdn.ok:
        lines.append(
            "media.discordapp.net (картинки) работает, cdn.discordapp.com (вложения) — нет. Раньше Blockcheck считал их "
            "OR-альтернативами одной фазы и принимал стратегию по картинкам; теперь это две обязательные фазы профиля Discord desktop."
        )
    if all(item.ok for item in results):
        if attachment_url:
            lines.append("Все проверки прошли. Если в браузере вложение всё равно не качается, разница в браузере: см. ниже.")
        else:
            lines.append("Маленькие файлы проходят. Чтобы проверить объём, вставьте ссылку на настоящее вложение.")
    lines.append(
        "Discord открывает файлы-вложения во внешнем браузере — так устроен сам клиент. Браузер ходит не так, как Discord: "
        "Firefox может брать адрес через свой DoH (network.trr) и идти по HTTP/3 (UDP 443). Если здесь OK, а в браузере "
        "NS_ERROR_TIMEOUT, проверьте, что в пресете есть профиль для UDP 443/QUIC на discordapp.com, или выключите HTTP/3 в браузере для проверки."
    )
    return lines


def discord_attachments_probe_to_text(attachment_url: str = "", *, timeout: float = 6.0) -> str:
    targets = list(CONTROL_URLS)
    if attachment_url.strip():
        targets.append(("attachment", validate_attachment_url(attachment_url)))
    results = [transfer_probe(label, url, timeout=timeout, stall_seconds=timeout) for label, url in targets]
    lines = ["Discord: загрузка вложений по слоям (DNS → TCP → TLS → HTTP → объём)", ""]
    lines.extend(item.to_text() for item in results)
    if not attachment_url.strip():
        lines.extend(["", "Ссылка на вложение не задана: объём не проверялся (контрольные файлы меньше 16 КБ)."])
    lines.extend(["", "Вывод:"])
    lines.extend(f"• {line}" for line in interpret(results, attachment_url.strip()))
    lines.extend(["", "Только чтение: обычные HTTPS-запросы, firewall не менялся."])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """`python3 -m zap2_gui.adapters.discord_media_probe [URL]`."""

    import sys

    args = sys.argv[1:] if argv is None else argv
    try:
        print(discord_attachments_probe_to_text(args[0] if args else ""))
    except ValueError as exc:
        print(f"Проверка вложений: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI
    raise SystemExit(main())


__all__ = [
    "TransferResult",
    "discord_attachments_probe_to_text",
    "interpret",
    "transfer_probe",
    "validate_attachment_url",
]
