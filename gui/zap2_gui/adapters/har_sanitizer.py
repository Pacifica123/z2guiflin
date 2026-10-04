#!/usr/bin/env python3
"""HAR sanitizer: strip credentials and personal data, keep network evidence.

The same file ships twice: as the independent script ``har_sanitize.py`` and as
``zap2_gui.adapters.har_sanitizer`` behind the GUI button. It needs only the
standard library (Python >= 3.8) and never touches the network.

The sanitizer is default-deny. A value survives only when a rule says it is
network evidence: hostnames, route-like path segments, methods, statuses,
protocol versions, timings, sizes, server addresses, error codes, header names
and an allowlist of transport/CDN header values. Everything else is replaced:

* secrets and opaque values become ``REDACTED_<hmac10>`` - a keyed HMAC, so the
  same value maps to the same marker and correlation survives;
* identifiers inside URL paths become shape-preserving pseudonyms (digit ->
  digit, letter -> letter), so URL parsers and path-pattern grouping still work;
* request/response bodies and WebSocket payloads are dropped, only sizes stay.

A final pass re-scans the result for every value that was redacted anywhere and
for known token formats, so a secret repeated in an unexpected field is caught.
The key is random per run unless ``--salt`` is given, and it is never stored.

Usage::

    python har_sanitize.py capture.har                  # -> capture.sanitized.har
    python har_sanitize.py --profile strict a.har b.zip --out-dir clean/
    python har_sanitize.py --help

Limits: hostnames and ordinary words in URL paths are kept on purpose - they are
the evidence. Review the result before publishing it.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from functools import lru_cache
import gzip
import hashlib
import hmac
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import sys
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple
from urllib.parse import unquote_plus, urlsplit, urlunsplit
import zipfile
import zlib

TOOL_NAME = "har-sanitizer"
TOOL_VERSION = "1.0.0"
PROFILE_BALANCED = "balanced"
PROFILE_STRICT = "strict"
PROFILES = (PROFILE_BALANCED, PROFILE_STRICT)
SANITIZED_SUFFIX = ".sanitized.har"
MARKER_PREFIX = "REDACTED_"
ERROR_BODY_LIMIT = 4096
_REBASE_ORIGIN = datetime(2000, 1, 1, tzinfo=timezone.utc)

# Header values that describe transport, caching or CDN behaviour.
_STRICT_HEADER_VALUES = frozenset(
    """:method :scheme :status accept-ranges age alt-svc alt-used cache-control cf-cache-status connection
    content-encoding content-length content-range content-type range retry-after sec-websocket-extensions
    sec-websocket-version server strict-transport-security transfer-encoding upgrade via x-cache
    x-firefox-http3 x-firefox-spdy""".split()
)
_BALANCED_HEADER_VALUES = _STRICT_HEADER_VALUES | frozenset(
    """accept accept-ch accept-encoding access-control-allow-credentials access-control-allow-headers
    access-control-allow-methods access-control-expose-headers access-control-max-age
    access-control-request-headers access-control-request-method allow cdn-cache-control
    content-security-policy cross-origin-embedder-policy cross-origin-opener-policy
    cross-origin-resource-policy date dnt expires keep-alive last-modified origin-agent-cluster
    permissions-policy pragma priority proxy-connection referrer-policy sec-ch-ua sec-ch-ua-mobile
    sec-ch-ua-platform sec-fetch-dest sec-fetch-mode sec-fetch-site sec-fetch-user sec-gpc server-timing te
    timing-allow-origin trailer upgrade-insecure-requests vary x-amz-cf-pop x-cache-hits x-cache-status
    x-content-type-options x-dns-prefetch-control x-envoy-upstream-service-time x-frame-options
    x-powered-by x-ratelimit-global x-ratelimit-limit x-ratelimit-remaining x-ratelimit-reset
    x-ratelimit-reset-after x-ratelimit-scope x-robots-tag x-served-by x-timer x-xss-protection
    x-youtube-client-name x-youtube-client-version""".split()
)
_DATE_HEADERS = frozenset({"date", "expires", "last-modified"})
_URL_HEADERS = frozenset(
    {":path", "access-control-allow-origin", "content-location", "location", "origin", "referer",
     "sec-websocket-origin", "x-origin"}
)
_HOST_HEADERS = frozenset({":authority", "host"})
_COOKIE_ATTRIBUTES = frozenset(
    {"domain", "expires", "httponly", "max-age", "partitioned", "path", "priority", "samesite", "secure"}
)

# Query parameters whose values describe the transfer rather than the user.
_SAFE_QUERY_KEYS = frozenset(
    """alr alt c clen compress count cver dpr dur encoding fmt format fvip gir h height initcwndbps itag
    keepalive limit lmt mime mm mode ms mt mv offset order page pl prettyprint quality range ratebypass
    rbuf requiressl rn sabr size sort source sparams svpuc txp type ump v ver version vprv w width
    xtags""".split()
)
_SHORT_QUERY_KEYS = frozenset(
    {"v", "ver", "version", "page", "limit", "offset", "count", "w", "h", "width", "height", "size", "dpr", "quality"}
)

# A path segment that follows one of these names is an identifier.
_ID_PARENTS = frozenset(
    """account accounts an_webp applications avatars banners call calls channel channels clip clips embed
    emojis gift gifts guild guilds id invite invites key keys live meeting meetings member members
    messages order orders org organizations orgs people playlist profile profiles project projects repo
    repos roles room rooms sb servers session sessions shorts stickers team teams threads ticket tickets
    token tokens uid user users vi vi_webp video videos watch webhooks workspace workspaces""".split()
)
_YOUTUBE_ID_PARENTS = frozenset({"c", "e", "u", "v"})
_YOUTUBE_HOSTS = ("youtube.com", "youtu.be", "ytimg.com", "youtube-nocookie.com")
_URL_PREFIXES = ("/", "http://", "https://", "ws://", "wss://", "blob:")
_MASK_REST_PARENTS = frozenset({"attachments", "ephemeral-attachments", "external"})
_ROUTE_WORDS = frozenset(
    """@me ack all batch billing bulk bulk-delete callback connections count create delete edit experiments
    info latest library list login logout me metadata new oauth2 pins premium profile register
    relationships science search self settings track typing verify""".split()
)
_FILE_EXTENSIONS = frozenset(
    """aspx avif bin bmp br cgi css eot gif gz htm html ico jpeg jpg js json jsp m3u8 m4a m4s map mjs mp3 mp4
    mpd ogg opus otf pdf php png srt svg ts ttf txt vtt wasm wav webm webp woff woff2 xml zip""".split()
)
# Custom ("_"-prefixed) string fields are kept only under these enum-like keys.
_GENERIC_ENUM_KEYS = frozenset(
    """_connectionid _fromcache _priority _protocol _resourcetype _securitystate connection functionname
    httponly nexthopprotocol opcode protocol samesite scriptid secure type""".split()
)

_MARKER_RE = re.compile(r"REDACTED_[0-9a-f]{10}")
_RUN_RE = re.compile(r"[A-Za-z0-9_\-]{8,}")
_ATOM_RE = re.compile(r"[A-Za-z0-9_\-]+")
_SCHEME_RE = re.compile(r"^([A-Za-z][A-Za-z0-9+.\-]*):")
_LABEL = r"[a-z0-9_](?:[a-z0-9_\-]*[a-z0-9_])?"
_HOST_RE = re.compile(rf"(?:\*\.)?{_LABEL}(?:\.{_LABEL})*")
_UUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
_HEX_RE = re.compile(r"[0-9a-fA-F]+")
_VERSION_SEGMENT_RE = re.compile(r"v\d{1,3}(\.\d+)*")
_PLAIN_SEGMENT_RE = re.compile(r"[a-z][a-z_\-]{0,31}")
_WORD_TOKEN_RE = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+")
_BENIGN_SCALAR_RE = re.compile(r"[A-Za-z0-9 _.:/+\-,;=()\[\]*$<>]{0,80}")
_BENIGN_KEY_RE = re.compile(r"[A-Za-z_$:][A-Za-z0-9_$.\-:\[\]]{0,63}")
_QUERY_NAME_RE = re.compile(r"[A-Za-z0-9_$.\-:~\[\]]{1,64}")
_QUERY_VALUE_RE = re.compile(r"[A-Za-z0-9_.,:/+\-=]{1,64}")
_HEADER_NAME_RE = re.compile(r"[A-Za-z0-9:_\-.]{1,100}")
_MIME_RE = re.compile(r"[A-Za-z0-9!#$&^_.+\-]+/[A-Za-z0-9!#$&^_.+\-]+")
_ISO_TIME_RE = re.compile(r"(\d{4}-\d\d-\d\d)[T ](\d\d:\d\d:\d\d)(\.\d+)?\s*(Z|[+-]\d\d:?\d\d)?", re.I)
_CF_RAY_RE = re.compile(r"[0-9a-f]{12,20}-([A-Z]{3})")
_URL_IN_TEXT_RE = re.compile(r"\b(?:https?|wss?)://[^\s\"'<>\\)\]]+", re.I)
_IPV4_RE = re.compile(r"(?<![\w./])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])")
_IPV6_RE = re.compile(r"(?<![\w:.])(?:[0-9A-Fa-f]{0,4}:){2,7}[0-9A-Fa-f]{0,4}(?![\w:.])")
_LONG_TOKEN_RE = re.compile(r"[A-Za-z0-9_\-+/=]{32,}")
_LONG_DIGITS_RE = re.compile(r"(?<!\d)\d{15,}(?!\d)")
_HOME_PATH_RE = re.compile(r"(/home/|/Users/|\\Users\\)[^/\\\"'\r\n]+", re.I)
_SECRET_PATTERNS = (
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_\-]{6,}\.[A-Za-z0-9_\-]{6,}\.[A-Za-z0-9_\-]*")),
    ("discordToken", re.compile(
        r"\b(?:mfa\.[A-Za-z0-9_\-]{20,}|[A-Za-z0-9_\-]{23,28}\.[A-Za-z0-9_\-]{6}\.[A-Za-z0-9_\-]{27,})"
    )),
    ("authScheme", re.compile(r"\b(Bearer|Basic|Bot|Digest|Token)(\s+)(?!REDACTED_)([A-Za-z0-9._~+/=\-]{8,})", re.I)),
    ("email", re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}")),
)
_EMAIL_RE = _SECRET_PATTERNS[3][1]
_UA_BROWSERS = (
    ("Electron", r"Electron/(\d+)"), ("Edge", r"Edg(?:e|A|iOS)?/(\d+)"), ("Opera", r"OPR/(\d+)"),
    ("Yandex", r"YaBrowser/(\d+)"), ("Firefox", r"Firefox/(\d+)"), ("Chrome", r"Chrom(?:e|ium)/(\d+)"),
    ("Safari", r"Version/(\d+)[^ ]* (?:Mobile/\S+ )?Safari"),
)
_UA_SYSTEMS = (
    ("Android", "Android"), ("iPhone", "iOS"), ("iPad", "iOS"), ("Windows", "Windows"),
    ("Mac OS X", "macOS"), ("CrOS", "ChromeOS"), ("Linux", "Linux"),
)
_REPORT_LABELS = (
    ("cookieValues", "значения cookie"),
    ("headerValues", "значения заголовков"),
    ("queryValues", "значения query-параметров и полей форм"),
    ("pathSegments", "идентификаторы в путях URL"),
    ("requestBodies", "тела запросов"),
    ("responseBodies", "тела ответов"),
    ("errorBodiesKept", "тела ошибок оставлены после текстовой чистки"),
    ("webSocketPayloads", "сообщения WebSocket"),
    ("urlCredentials", "логины и пароли в URL"),
    ("fragments", "фрагменты URL (#...)"),
    ("serverIps", "адреса серверов скрыты"),
    ("otherStrings", "прочие строки"),
)


class HarSanitizeError(ValueError):
    """The input is not a readable HAR or the output path is not acceptable."""


@dataclass(frozen=True)
class SanitizeOptions:
    profile: str = PROFILE_BALANCED
    keep_error_bodies: bool = False
    drop_server_ips: bool = False
    rebase_time: bool = False
    salt: Optional[str] = None

    def __post_init__(self) -> None:
        if self.profile not in PROFILES:
            raise HarSanitizeError(f"неизвестный профиль очистки: {self.profile!r}; допустимы {', '.join(PROFILES)}")

    @property
    def strict(self) -> bool:
        return self.profile == PROFILE_STRICT

    @property
    def keeps_error_bodies(self) -> bool:
        return self.keep_error_bodies and not self.strict

    @property
    def hides_server_ips(self) -> bool:
        return self.strict or self.drop_server_ips

    @property
    def rebases_time(self) -> bool:
        return self.strict or self.rebase_time

    def new_key(self) -> bytes:
        """HMAC key for pseudonyms: derived from the salt, random otherwise."""
        return hashlib.sha256(self.salt.encode("utf-8")).digest() if self.salt else secrets.token_bytes(32)


@dataclass
class SanitizeReport:
    source_name: str
    profile: str
    entries: int = 0
    hosts: int = 0
    counts: Dict[str, int] = field(default_factory=dict)
    redacted_headers: Dict[str, int] = field(default_factory=dict)
    residual_replaced: int = 0
    leaks_remaining: int = 0
    warnings: Tuple[str, ...] = ()
    output_path: Optional[Path] = None
    input_bytes: int = 0
    output_bytes: int = 0

    @property
    def clean(self) -> bool:
        return self.leaks_remaining == 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool": TOOL_NAME,
            "version": TOOL_VERSION,
            "sourceName": self.source_name,
            "outputPath": str(self.output_path) if self.output_path else None,
            "profile": self.profile,
            "entries": self.entries,
            "hosts": self.hosts,
            "replaced": dict(self.counts),
            "redactedHeaderNames": dict(self.redacted_headers),
            "residualReplaced": self.residual_replaced,
            "leaksRemaining": self.leaks_remaining,
            "warnings": list(self.warnings),
        }

    def to_text(self) -> str:
        lines = [
            "HAR sanitizer: очистка завершена",
            f"источник: {self.source_name}",
            f"профиль: {self.profile}",
            f"записей: {self.entries}; уникальных хостов: {self.hosts}",
        ]
        if self.output_path is not None:
            lines.append(f"результат: {self.output_path}")
        if self.input_bytes and self.output_bytes:
            lines.append(f"размер: {self.input_bytes} -> {self.output_bytes} байт")
        lines.extend(["", "Заменено или удалено:"])
        lines.extend([f"  - {title}: {self.counts[key]}" for key, title in _REPORT_LABELS if self.counts.get(key)] or ["  - ничего"])
        if self.redacted_headers:
            ranked = sorted(self.redacted_headers.items(), key=lambda item: (-item[1], item[0]))
            lines.extend(["", "Заголовки со скрытыми значениями (имена сохранены):"])
            lines.extend(f"  - {name}: {count}" for name, count in ranked[:12])
            if len(ranked) > 12:
                lines.append(f"  - ... ещё {len(ranked) - 12}")
        kept = "хосты, маршруты путей, методы, статусы, версии HTTP, тайминги, размеры, коды ошибок,"
        lines.extend([
            "",
            f"Сохранено для анализа: {kept}",
            "имена заголовков, cookie и параметров, транспортные и CDN-заголовки"
            + ("." if self.profile == PROFILE_STRICT else ", адреса серверов."),
            "",
            f"Контрольный проход: доочищено повторов секретов — {self.residual_replaced}; "
            f"осталось подозрительных совпадений — {self.leaks_remaining}.",
        ])
        if not self.clean:
            lines.append("ВНИМАНИЕ: контрольная проверка не пройдена; не передавайте файл без ручного просмотра.")
        lines.append("Граница: имена хостов и обычные слова в путях остаются как есть; перед публикацией просмотрите файл.")
        if self.warnings:
            lines.extend(["", "Предупреждения:"])
            lines.extend(f"  - {item}" for item in self.warnings)
        return "\n".join(lines)


def _is_wordy(core: str) -> bool:
    """True for identifiers assembled from readable words: getAccountInfo, Windows10Pro."""
    tokens = _WORD_TOKEN_RE.findall(core)
    words = [token for token in tokens if not token.isdigit()]
    if "".join(tokens) != core or not words or min(len(word) for word in words) < 2:
        return False
    return sum(len(word) for word in words) >= 3 * len(words)


@lru_cache(maxsize=65536)
def looks_random(value: str, *, min_len: int = 8) -> bool:
    """Heuristic for opaque identifiers and tokens made of [A-Za-z0-9_-]."""
    core = value.replace("-", "").replace("_", "")
    if len(value) < min_len or not core or not core.isascii() or not core.isalnum():
        return False
    digits = sum(ch.isdigit() for ch in core)
    if digits == len(core):
        return digits >= 12
    upper = any(ch.isupper() for ch in core)
    lower = any(ch.islower() for ch in core)
    if digits == 0:
        return upper and lower and len(core) >= 10 and not _is_wordy(core)
    if upper and lower:
        return not _is_wordy(core)
    switches = sum(1 for left, right in zip(core, core[1:]) if left.isdigit() != right.isdigit())
    return switches >= 3 or (len(core) >= 12 and _HEX_RE.fullmatch(core) is not None)


def _secret_is_real(name: str, match: "re.Match[str]") -> bool:
    if name != "authScheme":
        return True
    token = match.group(3)
    return len(token) >= 20 or any(ch.isdigit() for ch in token)


def _may_hold_secret_pattern(text: str) -> bool:
    # Every pattern needs a dot or whitespace; most HAR strings have neither.
    return len(text) >= 8 and ("." in text or " " in text or "\t" in text)


def _count_secret_patterns(text: str) -> int:
    if not _may_hold_secret_pattern(text):
        return 0
    return sum(1 for name, pattern in _SECRET_PATTERNS for match in pattern.finditer(text) if _secret_is_real(name, match))


def _is_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return False
    return True


def _has_ip_literal(text: str) -> bool:
    return any(_is_ip(match.group(0)) for pattern in (_IPV4_RE, _IPV6_RE) for match in pattern.finditer(text))


def _parse_time(value: str) -> Optional[datetime]:
    match = _ISO_TIME_RE.fullmatch(value.strip())
    if not match:
        return None
    date_part, clock, fraction, zone = match.groups()
    micro = int(((fraction or ".0")[1:] + "000000")[:6])
    try:
        moment = datetime.strptime(f"{date_part}T{clock}", "%Y-%m-%dT%H:%M:%S").replace(microsecond=micro)
    except ValueError:
        return None
    offset = timedelta(0)
    if zone and zone.upper() != "Z":
        digits = zone[1:].replace(":", "")
        offset = timedelta(hours=int(digits[:2]), minutes=int(digits[2:4])) * (-1 if zone[0] == "-" else 1)
    try:
        return (moment - offset).replace(tzinfo=timezone.utc)
    except OverflowError:
        return None


def _format_time(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%S.") + f"{moment.microsecond // 1000:03d}Z"


def _clean_mime(value: Any) -> str:
    text = str(value or "").strip()
    base = text.split(";", 1)[0].strip().lower()
    if not _MIME_RE.fullmatch(base):
        return base if re.fullmatch(r"[a-z0-9.+\-]{1,40}", base) and not looks_random(base) else ""
    charset = re.search(r"charset\s*=\s*\"?([A-Za-z0-9_\-]{1,24})", text, re.I)
    return f"{base}; charset={charset.group(1).lower()}" if charset else base


def _generalize_user_agent(value: str) -> str:
    """Keep only the browser family, its major version and the OS family."""
    browser = ""
    for name, pattern in _UA_BROWSERS:
        match = re.search(pattern, value)
        if match:
            browser = f"{name}/{match.group(1)}"
            break
    system = next((label for needle, label in _UA_SYSTEMS if needle in value), "")
    return "; ".join(part for part in (browser, system) if part)


class _Sanitizer:
    def __init__(self, options: SanitizeOptions, key: Optional[bytes] = None) -> None:
        self.options = options
        self._key = key or options.new_key()
        self.stats: Counter = Counter()
        self.redacted_headers: Counter = Counter()
        self.tainted: Set[str] = set()  # opaque runs: replaced wherever they reappear
        self.tainted_words: Set[str] = set()  # readable identifiers: replaced only as URL path segments
        self.protected: Set[str] = set()  # host labels: never replaced
        self.hosts: Set[str] = set()
        self.page_ids: Dict[str, str] = {}
        self._markers: Dict[str, str] = {}
        self.shift = timedelta(0)
        self.safe_headers = _STRICT_HEADER_VALUES if options.strict else _BALANCED_HEADER_VALUES
        if options.rebases_time:
            self.safe_headers = self.safe_headers - _DATE_HEADERS

    # -- pseudonyms ---------------------------------------------------------

    def _stream(self, purpose: str, value: str, size: int) -> bytes:
        seed = f"{purpose}\0{value}".encode("utf-8", "surrogatepass")
        blocks: List[bytes] = []
        while len(blocks) * 32 < size:
            blocks.append(hmac.new(self._key, seed + len(blocks).to_bytes(4, "big"), hashlib.sha256).digest())
        return b"".join(blocks)

    def remember(self, value: str, *, force: bool = False) -> None:
        """Record opaque runs of a redacted value so the final pass can find repeats.

        ``force`` also records readable runs: used when the position alone proves
        that the value is an identifier, e.g. a name after ``/users/``.
        """
        for run in _RUN_RE.findall(value[:65536]):
            if _MARKER_RE.fullmatch(run):
                continue
            if looks_random(run):
                self.tainted.add(run)
            elif force:
                self.tainted_words.add(run)

    def marker(self, value: Any, *, stat: str = "") -> str:
        text = str(value)
        if _MARKER_RE.fullmatch(text):
            return text
        if stat:
            self.stats[stat] += 1
        if text not in self._markers:
            self.remember(text)
            self._markers[text] = MARKER_PREFIX + self._stream("marker", text, 5)[:5].hex()
        return self._markers[text]

    def shaped(self, value: str, *, force: bool = False) -> str:
        """Pseudonym that keeps length and character classes; separators stay."""
        self.remember(value, force=force)
        span = 6 if _HEX_RE.fullmatch(value.replace("-", "")) else 26
        result = []
        for char, byte in zip(value, self._stream("shape", value, len(value))):
            if "0" <= char <= "9":
                result.append(chr(48 + byte % 10))
            elif "a" <= char <= "z":
                result.append(chr(97 + byte % span))
            elif "A" <= char <= "Z":
                result.append(chr(65 + byte % span))
            else:
                result.append(char)
        return "".join(result)

    # -- scalars ------------------------------------------------------------

    def benign(self, value: Any, *, limit: int = 80) -> Optional[str]:
        """Return an enum-like string unchanged, or None when it must be replaced."""
        text = str(value)
        if len(text) > limit or not _BENIGN_SCALAR_RE.fullmatch(text):
            return None
        if any(looks_random(run) for run in _RUN_RE.findall(text)) or _count_secret_patterns(text):
            return None
        return None if _has_ip_literal(text) else text

    def scalar(self, value: Any, *, stat: str = "otherStrings", limit: int = 80) -> Any:
        if value is None or isinstance(value, (bool, int, float)):
            return value
        kept = self.benign(value, limit=limit)
        return kept if kept is not None else self.marker(value, stat=stat)

    def time(self, value: Any) -> Any:
        if not isinstance(value, str):
            hidden = self.options.rebases_time and isinstance(value, (int, float)) and not isinstance(value, bool)
            return None if hidden else self.scalar(value)
        moment = _parse_time(value)
        if moment is None:
            return self.marker(value, stat="otherStrings") if value.strip() else ""
        return _format_time(moment - self.shift)

    def server_ip(self, value: Any) -> str:
        text = str(value or "").strip().strip("[]")
        if not text:
            return ""
        try:
            address = ipaddress.ip_address(text)
        except ValueError:
            return self.marker(text, stat="otherStrings")
        if self.options.hides_server_ips:
            self.stats["serverIps"] += 1
            return ""
        return str(address)

    def _scrub_patterns(self, text: str, *, residual: bool = False) -> str:
        if not _may_hold_secret_pattern(text):
            return text
        for name, pattern in _SECRET_PATTERNS:
            def replace(match: "re.Match[str]", _name: str = name) -> str:
                if not _secret_is_real(_name, match):
                    return match.group(0)
                if residual:
                    self.stats["residual"] += 1
                if _name == "authScheme":
                    return match.group(1) + match.group(2) + self.marker(match.group(3))
                return self.marker(match.group(0))
            text = pattern.sub(replace, text)
        return text

    def _scrub_plain(self, text: str) -> str:
        if not text:
            return text

        def ip_literal(match: "re.Match[str]") -> str:
            return self.marker(match.group(0)) if _is_ip(match.group(0)) else match.group(0)

        def long_token(match: "re.Match[str]") -> str:
            core = re.sub(r"[+/=]", "", match.group(0))
            return self.marker(match.group(0)) if looks_random(core) else match.group(0)

        text = self._scrub_patterns(text)
        text = _HOME_PATH_RE.sub(lambda match: match.group(1) + "REDACTED", text)
        text = _IPV6_RE.sub(ip_literal, _IPV4_RE.sub(ip_literal, text))
        text = _LONG_TOKEN_RE.sub(long_token, text)
        return _LONG_DIGITS_RE.sub(lambda match: self.shaped(match.group(0)), text)

    def text(self, value: Any, *, limit: int = 2048) -> str:
        """Scrub free text: URLs are sanitized, tokens, e-mail and IP literals replaced."""
        raw = str(value or "")
        pieces: List[str] = []
        cursor = 0
        for match in _URL_IN_TEXT_RE.finditer(raw):
            found = match.group(0).rstrip(".,;")
            pieces.append(self._scrub_plain(raw[cursor:match.start()]))
            pieces.append(self.url(found))
            cursor = match.start() + len(found)
        pieces.append(self._scrub_plain(raw[cursor:]))
        result = "".join(pieces)
        return result if len(result) <= limit else result[:limit] + "...[truncated]"

    # -- URLs ---------------------------------------------------------------

    def host(self, value: str, *, record: bool = False) -> str:
        host = value.strip().rstrip(".").lower()
        if not host:
            return ""
        try:
            ipaddress.ip_address(host.strip("[]"))
            host = host.strip("[]")
        except ValueError:
            if not _HOST_RE.fullmatch(host):
                try:
                    host = host.encode("idna").decode("ascii")
                except UnicodeError:
                    host = ""
                if not _HOST_RE.fullmatch(host):
                    return self.marker(value, stat="otherStrings")
            # Host labels are evidence: the final pass must never rewrite them.
            self.protected.update(host.split("."))
        if record:
            self.hosts.add(host)
        return host

    def url(self, value: Any, base_host: str = "") -> str:
        text = str(value or "").strip()
        if not text or _MARKER_RE.fullmatch(text):
            return text
        scheme_match = _SCHEME_RE.match(text)
        scheme = scheme_match.group(1).lower() if scheme_match else ""
        if scheme in {"http", "https", "ws", "wss"}:
            try:
                parts = urlsplit(text)
                host = parts.hostname or ""
            except ValueError:
                return self.marker(text, stat="otherStrings")
            try:
                port = parts.port
            except ValueError:
                port = None
            if parts.username or parts.password:
                self.stats["urlCredentials"] += 1
                self.remember(f"{parts.username or ''} {parts.password or ''}", force=True)
            host = self.host(host)
            netloc = (f"[{host}]" if ":" in host else host) + (f":{port}" if port else "")
            fragment = ""
            if parts.fragment:
                self.stats["fragments"] += 1
                self.remember(parts.fragment)
                fragment = "REDACTED"
            return urlunsplit((scheme, netloc, self.path(parts.path, host), self.query(parts.query), fragment))
        if scheme == "data":
            mime = _clean_mime(text[5:].split(",", 1)[0])
            self.stats["otherStrings"] += 1
            return f"data:{mime};REDACTED" if mime else "data:REDACTED"
        if scheme == "blob":
            return "blob:" + self.url(text[5:])
        if scheme == "about" and re.fullmatch(r"about:[a-z\-]{1,32}", text.lower()):
            return text.lower()
        if scheme:
            # Extension, file and other local schemes identify the browser profile.
            return f"{scheme}:{self.marker(text, stat='otherStrings')}"
        if text.startswith("//"):
            return self.url("https:" + text)[len("https:"):]
        if text.startswith("/"):
            head, hash_sep, fragment = text.partition("#")
            path, query_sep, query = head.partition("?")
            if fragment:
                self.stats["fragments"] += 1
                self.remember(fragment)
            tail = (query_sep + self.query(query) if query_sep else "") + ("#REDACTED" if hash_sep else "")
            return self.path(path, base_host) + tail
        return self.marker(text, stat="otherStrings")

    @staticmethod
    def _split_extension(segment: str) -> Tuple[str, str]:
        stem, dot, extension = segment.rpartition(".")
        if dot and stem and extension.lower() in _FILE_EXTENSIONS:
            return stem, "." + extension
        return segment, ""

    @staticmethod
    def _atom_is_identifier(atom: str) -> bool:
        if atom.isdigit():
            return len(atom) >= 6
        return looks_random(atom) or (len(atom) >= 24 and any(char.isdigit() for char in atom))

    def _mask_segment(self, segment: str, parent: str, youtube: bool, forced: bool) -> Optional[str]:
        """Return the pseudonymized segment, or None when the segment is route evidence."""
        low = segment.lower()
        if not forced and (low == "@me" or _VERSION_SEGMENT_RE.fullmatch(low)):
            return None
        if not segment.isascii() or "%" in segment:
            return self.marker(segment)
        stem, extension = self._split_extension(segment)
        whole = forced or segment.startswith("@") or "=" in segment or ";" in segment
        whole = whole or _EMAIL_RE.fullmatch(segment) is not None
        if not whole and self.options.strict:
            whole = not (_PLAIN_SEGMENT_RE.fullmatch(stem) or (stem.isdigit() and len(stem) < 6))
        if not whole and (parent in _ID_PARENTS or (youtube and parent in _YOUTUBE_ID_PARENTS)):
            whole = low not in _ROUTE_WORDS and low not in _ID_PARENTS
        if whole:
            return self.shaped(stem, force=True) + extension
        if not any(self._atom_is_identifier(atom) for atom in _ATOM_RE.findall(stem)):
            return None

        def mask_atom(match: "re.Match[str]") -> str:
            atom = match.group(0)
            return self.shaped(atom) if self._atom_is_identifier(atom) else atom

        # Only the opaque parts change: "web.8f3a9c1e.js" keeps its readable name.
        return _ATOM_RE.sub(mask_atom, stem) + extension

    def path(self, value: str, host: str = "") -> str:
        if not value:
            return value
        youtube = host.endswith(_YOUTUBE_HOSTS)
        result: List[str] = []
        parent = ""
        mask_rest = False
        for segment in value.split("/"):
            masked = self._mask_segment(segment, parent, youtube, mask_rest) if segment else None
            if masked is not None:
                self.stats["pathSegments"] += 1
            result.append(segment if masked is None else masked)
            if segment:
                parent = segment.lower()
                mask_rest = mask_rest or parent in _MASK_REST_PARENTS
        return "/".join(result)

    def _query_name(self, raw: str) -> str:
        decoded = unquote_plus(raw)
        if _QUERY_NAME_RE.fullmatch(raw) and not looks_random(decoded):
            return raw
        return self.marker(decoded, stat="queryValues")

    def _query_value(self, name: str, decoded: str, raw: Optional[str] = None) -> str:
        if decoded == "":
            return ""
        key = unquote_plus(name).lower()
        if not self.options.strict and key in _SAFE_QUERY_KEYS and _QUERY_VALUE_RE.fullmatch(decoded):
            opaque = any(looks_random(run) for run in _RUN_RE.findall(decoded))
            oversized = key in _SHORT_QUERY_KEYS and (len(decoded) > 8 or not decoded.replace(".", "").isalnum())
            if not opaque and not oversized:
                return decoded if raw is None else raw
        return self.marker(decoded, stat="queryValues")

    def query(self, value: str) -> str:
        pairs = []
        for pair in value.split("&") if value else ():
            if not pair:
                continue
            name, separator, raw = pair.partition("=")
            clean = self._query_name(name)
            pairs.append(clean + separator + self._query_value(name, unquote_plus(raw), raw) if separator else clean)
        return "&".join(pairs)

    # -- headers and cookies ------------------------------------------------

    def _cookie_name(self, value: Any) -> str:
        name = str(value or "").strip()
        if not name:
            return ""
        if not name.isascii() or len(name) > 96 or re.search(r"[\s;=,]", name):
            return self.marker(name, stat="otherStrings")
        return self.shaped(name) if looks_random(name) or _UUID_RE.search(name) else name

    def _cookie_pair(self, chunk: str) -> str:
        name, separator, raw = chunk.strip().partition("=")
        clean = self._cookie_name(name)
        if not separator:
            return clean
        return clean + "=" + (self.marker(raw, stat="cookieValues") if raw else "")

    def _set_cookie(self, line: str) -> str:
        chunks = [chunk.strip() for chunk in line.split(";") if chunk.strip()]
        if not chunks:
            return ""
        parts = [self._cookie_pair(chunks[0])]
        for attribute in chunks[1:]:
            key, separator, raw = attribute.partition("=")
            key, raw = key.strip(), raw.strip()
            low = key.lower()
            if low not in _COOKIE_ATTRIBUTES:
                parts.append(self.marker(attribute, stat="otherStrings"))
            elif not separator:
                parts.append(key)
            elif low == "path":
                parts.append(f"{key}={self.path(raw)}")
            elif low == "domain":
                parts.append(f"{key}={'.' if raw.startswith('.') else ''}{self.host(raw.lstrip('.'))}")
            elif low == "expires":
                parts.append(f"{key}=REDACTED" if self.options.rebases_time else f"{key}={self.text(raw, limit=64)}")
            else:
                parts.append(f"{key}={self.scalar(raw)}")
        return "; ".join(parts)

    def _header_value(self, name: str, value: str, host: str) -> str:
        low = name.lower()
        if low == "cookie":
            return "; ".join(self._cookie_pair(chunk) for chunk in value.split(";") if chunk.strip())
        if low == "set-cookie":
            # Firefox joins several Set-Cookie headers with a newline.
            return "\n".join(filter(None, (self._set_cookie(line) for line in value.split("\n"))))
        if low in _URL_HEADERS:
            return value if value.strip() in {"*", "null", ""} else self.url(value, host)
        if low in _HOST_HEADERS:
            name_part, colon, port = value.strip().rpartition(":")
            if colon and port.isdigit() and "]" not in port:
                return f"{self.host(name_part.strip('[]'))}:{port}"
            return self.host(value.strip().strip("[]"))
        if low == "user-agent" and not self.options.strict:
            general = _generalize_user_agent(value)
            if general:
                self.stats["headerValues"] += 1
                return general
        if low == "cf-ray":
            match = _CF_RAY_RE.fullmatch(value.strip())
            if match:
                return f"{self.marker(value.strip(), stat='headerValues')}-{match.group(1)}"
        if low in self.safe_headers:
            return self.text(value, limit=8192)
        if value == "":
            return ""
        self.redacted_headers[low] += 1
        return self.marker(value, stat="headerValues")

    def headers(self, value: Any, host: str) -> List[Dict[str, str]]:
        result = []
        for item in value if isinstance(value, list) else ():
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()
            if not _HEADER_NAME_RE.fullmatch(name):
                name = self.marker(name, stat="otherStrings")
            result.append({"name": name, "value": self._header_value(name, str(item.get("value", "")), host)})
        return result

    def cookies(self, value: Any) -> List[Dict[str, Any]]:
        result = []
        for item in value if isinstance(value, list) else ():
            if not isinstance(item, dict):
                continue
            cookie: Dict[str, Any] = {}
            for key, raw in item.items():
                if key == "name":
                    cookie[key] = self._cookie_name(raw)
                elif key == "value":
                    cookie[key] = self.marker(raw, stat="cookieValues") if str(raw) != "" else ""
                elif key == "path":
                    cookie[key] = self.path(str(raw or ""))
                elif key == "domain":
                    text = str(raw or "").strip()
                    cookie[key] = ("." if text.startswith(".") else "") + self.host(text.lstrip("."))
                elif key == "expires":
                    cookie[key] = self.time(raw)
                elif key != "comment":
                    cookie[key] = self.generic(raw, key)
            result.append(cookie)
        return result

    # -- bodies -------------------------------------------------------------

    def post_data(self, value: Any) -> Any:
        if not isinstance(value, dict):
            return None
        result: Dict[str, Any] = {"mimeType": _clean_mime(value.get("mimeType"))}
        if isinstance(value.get("params"), list):
            params = []
            for item in value["params"]:
                if not isinstance(item, dict):
                    continue
                param: Dict[str, Any] = {"name": self._query_name(str(item.get("name", "")))}
                if "value" in item:
                    param["value"] = self.marker(item["value"], stat="queryValues") if str(item["value"]) != "" else ""
                if "fileName" in item:
                    param["fileName"] = self.marker(item["fileName"], stat="otherStrings")
                if "contentType" in item:
                    param["contentType"] = _clean_mime(item["contentType"])
                params.append(param)
            result["params"] = params
        text = value.get("text")
        if "text" in value:
            result["text"] = ""
        if isinstance(text, str) and text:
            self.stats["requestBodies"] += 1
            self.remember(text)
            result["_sanitized"] = {"removed": "text", "chars": len(text)}
        return result

    def content(self, value: Any, status: int) -> Dict[str, Any]:
        if not isinstance(value, dict):
            return {"size": 0, "mimeType": ""}
        mime = _clean_mime(value.get("mimeType"))
        result: Dict[str, Any] = {"size": self.scalar(value.get("size", 0)), "mimeType": mime}
        if "compression" in value:
            result["compression"] = self.scalar(value["compression"])
        text = value.get("text")
        if isinstance(text, str) and text:
            readable = mime.startswith("text/") or any(kind in mime for kind in ("json", "xml", "html"))
            failed = status == 0 or status >= 400
            if self.options.keeps_error_bodies and failed and readable and value.get("encoding") != "base64":
                self.stats["errorBodiesKept"] += 1
                result["text"] = self.text(text[:ERROR_BODY_LIMIT], limit=ERROR_BODY_LIMIT * 2)
                result["_sanitized"] = {"kept": "scrubbed-error-body", "chars": len(text), "truncated": len(text) > ERROR_BODY_LIMIT}
            else:
                self.stats["responseBodies"] += 1
                result["_sanitized"] = {"removed": "text", "chars": len(text), "encoding": self.scalar(value.get("encoding") or "")}
        return result

    def websocket(self, value: Any) -> List[Dict[str, Any]]:
        result = []
        for item in value if isinstance(value, list) else ():
            if not isinstance(item, dict):
                continue
            message: Dict[str, Any] = {}
            for key, raw in item.items():
                if key == "data":
                    self.stats["webSocketPayloads"] += 1
                    message["data"] = ""
                    message["_dataLength"] = len(raw) if isinstance(raw, str) else 0
                elif key == "time" and isinstance(raw, (int, float)) and not isinstance(raw, bool):
                    # Epoch seconds: follow the same shift as startedDateTime.
                    message[key] = round(raw - self.shift.total_seconds(), 6)
                else:
                    message[key] = self.generic(raw, key)
            result.append(message)
        return result

    # -- generic default-deny walker for custom "_" fields ------------------

    def generic(self, value: Any, key: str = "", depth: int = 0) -> Any:
        if isinstance(value, int) and not isinstance(value, bool) and abs(value) >= 10 ** 16:
            self.stats["otherStrings"] += 1
            return int(self.shaped(str(abs(value))))  # snowflake-sized: an identifier, not a size
        if value is None or isinstance(value, (bool, int, float)):
            return value
        if depth > 40:
            return None
        if isinstance(value, list):
            return [self.generic(item, key, depth + 1) for item in value]
        if isinstance(value, dict):
            result: Dict[str, Any] = {}
            for name, item in value.items():
                name = str(name)
                if name == "comment" or (name == "stack" and self.options.strict):
                    continue
                benign_key = _BENIGN_KEY_RE.fullmatch(name) and not looks_random(name)
                result[name if benign_key else self.marker(name, stat="otherStrings")] = self.generic(item, name, depth + 1)
            return result
        text = str(value)
        low = key.lower()
        if text == "":
            return ""
        if "url" in low or low in {"href", "origin", "referrer"} or re.match(r"(?:https?|wss?|data|blob):", text, re.I):
            return self.url(text)
        if "error" in low or "failure" in low:
            return self.text(text, limit=400)
        if _parse_time(text):
            return self.time(text)
        if low in _GENERIC_ENUM_KEYS and " " not in text:
            return self.scalar(text, limit=48)
        return self.marker(text, stat="otherStrings")

    # -- HAR structure ------------------------------------------------------

    def page_id(self, value: Any) -> str:
        key = str(value or "")
        if key not in self.page_ids:
            self.page_ids[key] = key if re.fullmatch(r"page_\d{1,6}", key) else f"page_s{len(self.page_ids) + 1}"
        return self.page_ids[key]

    def page(self, value: Dict[str, Any]) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        for key, raw in value.items():
            if key == "id":
                result[key] = self.page_id(raw)
            elif key == "startedDateTime":
                result[key] = self.time(raw)
            elif key == "title":
                # Browsers put the page URL here; a real page title is free text.
                title = str(raw or "").strip()
                if _SCHEME_RE.match(title) and " " not in title:
                    result[key] = self.url(title)
                else:
                    result[key] = self.marker(title, stat="otherStrings") if title else ""
            elif key != "comment":
                result[key] = self.generic(raw, key)
        return result

    def request(self, value: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
        url = self.url(value.get("url", ""))
        try:
            host = urlsplit(url).hostname or ""
        except ValueError:
            host = ""
        result: Dict[str, Any] = {}
        for key, raw in value.items():
            if key == "url":
                result[key] = url
            elif key == "method":
                method = str(raw or "").upper()
                result[key] = method if re.fullmatch(r"[A-Z]{1,16}", method) else self.scalar(raw)
            elif key == "httpVersion":
                result[key] = self.scalar(raw, limit=24)
            elif key == "headers":
                result[key] = self.headers(raw, host)
            elif key == "cookies":
                result[key] = self.cookies(raw)
            elif key == "queryString":
                result[key] = [
                    {"name": self._query_name(str(item.get("name", ""))),
                     "value": self._query_value(str(item.get("name", "")), str(item.get("value", "")))}
                    for item in (raw if isinstance(raw, list) else ()) if isinstance(item, dict)
                ]
            elif key == "postData":
                result[key] = self.post_data(raw)
            elif key != "comment":
                result[key] = self.generic(raw, key)
        return result, host

    def response(self, value: Dict[str, Any], host: str) -> Dict[str, Any]:
        try:
            status = int(value.get("status", 0) or 0)
        except (TypeError, ValueError):
            status = 0
        result: Dict[str, Any] = {}
        for key, raw in value.items():
            if key == "statusText":
                result[key] = self.text(raw, limit=200)
            elif key == "httpVersion":
                result[key] = self.scalar(raw, limit=24)
            elif key == "headers":
                result[key] = self.headers(raw, host)
            elif key == "cookies":
                result[key] = self.cookies(raw)
            elif key == "content":
                result[key] = self.content(raw, status)
            elif key == "redirectURL":
                result[key] = self.url(raw, host) if raw else ""
            elif key != "comment":
                result[key] = self.generic(raw, key)
        return result

    def entry(self, value: Dict[str, Any]) -> Dict[str, Any]:
        request, host = self.request(value["request"]) if isinstance(value.get("request"), dict) else ({}, "")
        result: Dict[str, Any] = {}
        for key, raw in value.items():
            if key == "request":
                result[key] = request
            elif key == "pageref":
                result[key] = self.page_id(raw)
            elif key == "startedDateTime":
                result[key] = self.time(raw)
            elif key == "response":
                result[key] = self.response(raw, host) if isinstance(raw, dict) else {}
            elif key == "serverIPAddress":
                result[key] = self.server_ip(raw)
            elif key == "_webSocketMessages":
                result[key] = self.websocket(raw)
            elif key != "comment":
                result[key] = self.generic(raw, key)
        return result

    def run(self, data: Dict[str, Any]) -> Dict[str, Any]:
        log = data.get("log")
        if not isinstance(log, dict) or not isinstance(log.get("entries"), list):
            raise HarSanitizeError("это не HAR: отсутствует log.entries")
        entries = [item for item in log["entries"] if isinstance(item, dict)]
        raw_pages = log.get("pages")
        pages = [item for item in raw_pages if isinstance(item, dict)] if isinstance(raw_pages, list) else []
        if self.options.rebases_time:
            starts = [_parse_time(str(item.get("startedDateTime", ""))) for item in [*pages, *entries]]
            known = [moment for moment in starts if moment is not None]
            if known:
                self.shift = min(known) - _REBASE_ORIGIN
        # Request hosts are collected first so that the final pass never rewrites them.
        for item in entries:
            request = item.get("request")
            if not isinstance(request, dict):
                continue
            try:
                parts = urlsplit(str(request.get("url", "")))
            except ValueError:
                continue
            if parts.scheme.lower() in {"http", "https", "ws", "wss"}:
                self.host(parts.hostname or "", record=True)
        result: Dict[str, Any] = {}
        for key, raw in log.items():
            if key == "entries":
                result[key] = [self.entry(item) for item in entries]
            elif key == "pages":
                result[key] = [self.page(item) for item in pages]
            elif key in {"creator", "browser"} and isinstance(raw, dict):
                result[key] = {name: self.scalar(raw[name]) for name in ("name", "version") if name in raw}
            elif key == "version":
                result[key] = self.scalar(raw, limit=16)
            elif key not in {"comment", "_sanitizer"}:
                result[key] = self.generic(raw, key)
        return {"log": self.final_pass(result)}

    # -- final pass ---------------------------------------------------------

    def _repeats(self, text: str) -> List["re.Match[str]"]:
        """Runs of ``text`` that repeat a value redacted elsewhere in the file."""
        if len(text) < 8:
            return []
        in_url = text.startswith(_URL_PREFIXES)
        found = []
        for match in _RUN_RE.finditer(text):
            run = match.group(0)
            if run in self.protected:
                continue
            is_segment = in_url and text[max(match.start() - 1, 0)] == "/"
            if run in self.tainted or (is_segment and run in self.tainted_words):
                found.append(match)
        return found

    def _residual(self, text: str) -> str:
        pieces: List[str] = []
        cursor = 0
        for match in self._repeats(text):
            self.stats["residual"] += 1
            pieces.extend((text[cursor:match.start()], self.marker(match.group(0))))
            cursor = match.end()
        pieces.append(text[cursor:])
        return self._scrub_patterns("".join(pieces), residual=True)

    def final_pass(self, node: Any) -> Any:
        """Rewrite values only: keys are HAR schema names or markers already."""
        if isinstance(node, str):
            return self._residual(node)
        if isinstance(node, list):
            return [self.final_pass(item) for item in node]
        if isinstance(node, dict):
            return {key: self.final_pass(item) for key, item in node.items()}
        return node

    def count_leaks(self, node: Any) -> int:
        if isinstance(node, str):
            return len(self._repeats(node)) + _count_secret_patterns(node)
        if isinstance(node, list):
            return sum(self.count_leaks(item) for item in node)
        if isinstance(node, dict):
            return sum(self.count_leaks(item) for item in node.values())
        return 0


def sanitize_har_data(
    data: Any,
    options: Optional[SanitizeOptions] = None,
    *,
    source_name: str = "",
    key: Optional[bytes] = None,
) -> Tuple[Dict[str, Any], SanitizeReport]:
    """Return a sanitized copy of a parsed HAR and a report that holds counters only."""
    options = options or SanitizeOptions()
    if not isinstance(data, dict):
        raise HarSanitizeError("это не HAR: корень JSON должен быть объектом")
    warnings = []
    if isinstance(data.get("log"), dict) and "_sanitizer" in data["log"]:
        warnings.append("файл уже проходил очистку; повторный запуск заменяет псевдонимы новыми")
    worker = _Sanitizer(options, key)
    result = worker.run(data)
    residual = worker.stats.pop("residual", 0)
    leaks = worker.count_leaks(result)
    counts = {name: int(value) for name, value in sorted(worker.stats.items()) if value}
    result["log"]["_sanitizer"] = {
        "tool": TOOL_NAME,
        "version": TOOL_VERSION,
        "profile": options.profile,
        "options": {
            "errorBodies": "scrubbed" if options.keeps_error_bodies else "dropped",
            "serverIps": "dropped" if options.hides_server_ips else "kept",
            "time": "rebased-to-2000-01-01" if options.rebases_time else "utc",
            "pseudonymKey": "user-salt" if options.salt else "random-per-run",
        },
        "replaced": counts,
        "note": "REDACTED_<id> markers and path identifiers are keyed pseudonyms: equal inputs give equal outputs.",
    }
    if options.keeps_error_bodies:
        warnings.append("тела ошибок оставлены после текстовой чистки; это свободный текст, проверьте его вручную")
    report = SanitizeReport(
        source_name=source_name,
        profile=options.profile,
        entries=len(result["log"].get("entries", [])),
        hosts=len(worker.hosts),
        counts=counts,
        redacted_headers=dict(worker.redacted_headers),
        residual_replaced=int(residual),
        leaks_remaining=leaks,
        warnings=tuple(warnings),
    )
    return result, report


def _decode_json(payload: bytes) -> Any:
    try:
        if payload[:2] == b"\x1f\x8b":
            payload = gzip.decompress(payload)
        return json.loads(payload.decode("utf-8-sig", errors="replace"))
    except json.JSONDecodeError as exc:
        raise HarSanitizeError(f"файл не является корректным JSON: {exc}") from exc
    except (OSError, EOFError, zlib.error) as exc:
        raise HarSanitizeError(f"повреждённый gzip: {exc}") from exc


def read_har_documents(path: Path) -> List[Tuple[str, Any, int]]:
    """Read ``.har``, gzip-compressed HAR or every ``.har`` member of a zip archive."""
    if not path.is_file():
        raise HarSanitizeError(f"файл не найден: {path}")
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            names = sorted(name for name in archive.namelist() if name.lower().endswith(".har") and not name.endswith("/"))
            if not names:
                raise HarSanitizeError("zip-архив не содержит .har файлов")
            members = [(name, archive.read(name)) for name in names]
        single = len(members) == 1
        return [("" if single else name.replace("/", "."), _decode_json(payload), len(payload)) for name, payload in members]
    payload = path.read_bytes()
    return [("", _decode_json(payload), len(payload))]


def default_output_path(source: Path, member: str = "") -> Path:
    """``capture.har`` -> ``capture.sanitized.har`` next to the source."""
    stem = source.name
    for suffix in (".gz", ".zip", ".har"):
        if stem.lower().endswith(suffix):
            stem = stem[: -len(suffix)]
    if member:
        stem = f"{stem}.{Path(member).stem}"
    return source.with_name(stem + SANITIZED_SUFFIX)


def _write_json(path: Path, data: Any, *, compact: bool) -> int:
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":")) if compact else json.dumps(data, ensure_ascii=False, indent=2)
    payload = (text + "\n").encode("utf-8", errors="replace")  # lone surrogates from \uXXXX escapes
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp{os.getpid()}")
    try:
        temporary.write_bytes(payload)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()
    return len(payload)


def sanitize_har_file(
    source: Any,
    destination: Any = None,
    *,
    out_dir: Any = None,
    options: Optional[SanitizeOptions] = None,
    overwrite: bool = False,
    compact: bool = False,
    key: Optional[bytes] = None,
) -> List[SanitizeReport]:
    """Write sanitized copies of a HAR file or of each HAR inside a zip archive.

    The source is never modified. One report is returned per written file.
    """
    options = options or SanitizeOptions()
    source_path = Path(source).expanduser()
    documents = read_har_documents(source_path)
    if destination is not None and len(documents) > 1:
        raise HarSanitizeError("архив содержит несколько HAR; укажите каталог результата вместо одного файла")
    key = key or options.new_key()
    reports = []
    for member, data, size in documents:
        if destination is not None:
            target = Path(destination).expanduser()
        else:
            target = default_output_path(source_path, member)
            if out_dir is not None:
                target = Path(out_dir).expanduser() / target.name
        if target.resolve() == source_path.resolve():
            raise HarSanitizeError("результат совпадает с исходным файлом; исходный HAR не перезаписывается")
        if target.exists() and not overwrite:
            raise HarSanitizeError(f"файл результата уже существует: {target}")
        name = source_path.name + (f"::{member}" if member else "")
        sanitized, report = sanitize_har_data(data, options, source_name=name, key=key)
        report.input_bytes = size
        report.output_bytes = _write_json(target, sanitized, compact=compact)
        report.output_path = target
        reports.append(report)
    return reports


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Очистка HAR от чувствительных данных с сохранением сетевых признаков для анализа.",
        epilog="Исходный файл не изменяется. Результат по умолчанию: <имя>.sanitized.har рядом с исходным.",
    )
    parser.add_argument("inputs", nargs="+", metavar="HAR", help="файл .har, .har.gz или .zip с HAR внутри")
    parser.add_argument("-o", "--output", help="файл результата (только для одного входного HAR)")
    parser.add_argument("--out-dir", help="каталог для результатов вместо каталога исходного файла")
    parser.add_argument(
        "--profile", choices=PROFILES, default=PROFILE_BALANCED,
        help="balanced — максимум пользы для анализа (по умолчанию); strict — максимум очистки",
    )
    parser.add_argument(
        "--keep-error-bodies", action="store_true",
        help="оставить текст тел ответов с ошибками (до 4 КБ, после текстовой чистки); в strict игнорируется",
    )
    parser.add_argument("--drop-server-ips", action="store_true", help="не сохранять serverIPAddress")
    parser.add_argument("--rebase-time", action="store_true", help="сдвинуть время захвата к 2000-01-01, сохранив интервалы")
    parser.add_argument(
        "--salt",
        help="ключ псевдонимов: одинаковый ключ даёт одинаковые псевдонимы в разных запусках; держите его в секрете",
    )
    parser.add_argument("--compact", action="store_true", help="записать JSON без отступов")
    parser.add_argument("--force", action="store_true", help="перезаписать существующий файл результата")
    parser.add_argument("--report-json", help="сохранить отчёт (только счётчики) в JSON")
    parser.add_argument("-q", "--quiet", action="store_true", help="не печатать текстовый отчёт")
    parser.add_argument("--version", action="version", version=f"{TOOL_NAME} {TOOL_VERSION}")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Exit code: 0 - clean, 2 - input/output error, 3 - control check found leftovers."""
    args = build_parser().parse_args(argv)
    if args.output and (len(args.inputs) > 1 or args.out_dir):
        print("HAR sanitizer: --output применим к одному входному файлу и несовместим с --out-dir", file=sys.stderr)
        return 2
    reports: List[SanitizeReport] = []
    try:
        options = SanitizeOptions(
            profile=args.profile, keep_error_bodies=args.keep_error_bodies,
            drop_server_ips=args.drop_server_ips, rebase_time=args.rebase_time, salt=args.salt,
        )
        # One key for the whole batch keeps pseudonyms comparable across files.
        key = options.new_key()
        for raw in args.inputs:
            reports.extend(sanitize_har_file(
                raw, args.output, out_dir=args.out_dir, options=options,
                overwrite=args.force, compact=args.compact, key=key,
            ))
        if args.report_json:
            Path(args.report_json).expanduser().write_text(
                json.dumps([report.to_dict() for report in reports], ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
    except (HarSanitizeError, OSError, zipfile.BadZipFile, EOFError) as exc:
        print(f"HAR sanitizer: ошибка: {exc}", file=sys.stderr)
        return 2
    if not args.quiet:
        print("\n\n".join(report.to_text() for report in reports))
    return 0 if all(report.clean for report in reports) else 3


if __name__ == "__main__":
    raise SystemExit(main())
