"""Определение узла googlevideo, с которого этому пользователю отдаётся видео.

Видео YouTube идёт не с youtube.com, а с узлов вида rrN---sn-XXXX.googlevideo.com,
и узел у каждого провайдера свой. В hostlist это решается суффиксом
(`googlevideo.com` покрывает все узлы), а Blockcheck нужен конкретный хост.
Google сам сообщает узел по адресу клиента: redirector.googlevideo.com/report_mapping.

Только чтение: один HTTPS-запрос, без привилегий, firewall не трогается.
"""

from __future__ import annotations

import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable

REPORT_MAPPING_URL = "https://redirector.googlevideo.com/report_mapping?di=no"
REDIRECTOR_HOST = "redirector.googlevideo.com"
DEFAULT_TIMEOUT_SECONDS = 4.0
_MAX_BODY = 16 * 1024

# Строка ответа выглядит как «1.2.3.0/24 => sn-abcd1234-xyz5 : router: ...». Встречается и вариант
# с именем кластера («=> fra16s12»): из него имя узла без закрытой таблицы не получить, это честный отказ.
_NODE_RE = re.compile(r"=>\s*(sn-[a-z0-9]{2,40}(?:-[a-z0-9]{2,20}){0,3})(?![a-z0-9-])")
_CLUSTER_RE = re.compile(r"=>\s*([a-z]{3}\d{2}[a-z]\d{1,3})\b")

Fetcher = Callable[[str, float], str]


@dataclass(frozen=True)
class GooglevideoNode:
    node: str = ""
    host: str = ""
    error: str = ""

    @property
    def ok(self) -> bool:
        return bool(self.host)

    def to_text(self) -> str:
        if self.ok:
            return (
                f"googlevideo: узел {self.node} → {self.host}\n"
                f"источник: {REPORT_MAPPING_URL}\n"
                "В hostlist достаточно строки googlevideo.com: она покрывает все узлы."
            )
        return (
            f"googlevideo: узел не определён ({self.error}).\n"
            f"Проверяется {REDIRECTOR_HOST}: тот же SNI-суффикс googlevideo.com, но не тот же узел и не те же IP."
        )


def parse_report_mapping(text: str) -> str:
    """Вернуть идентификатор узла `sn-…` из ответа report_mapping или пустую строку."""

    match = _NODE_RE.search(text.lower())
    return match.group(1) if match else ""


def node_host(node: str, index: int = 1) -> str:
    return f"rr{index}---{node}.googlevideo.com"


def _urllib_fetch(url: str, timeout: float) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "zap2-gui"})
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed https URL
        return response.read(_MAX_BODY).decode("utf-8", errors="replace")


def resolve_googlevideo_node(fetch: Fetcher | None = None, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> GooglevideoNode:
    try:
        body = (fetch or _urllib_fetch)(REPORT_MAPPING_URL, timeout)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        reason = getattr(exc, "reason", None) or exc
        return GooglevideoNode(error=f"redirector не ответил: {reason}")
    node = parse_report_mapping(body)
    if not node:
        cluster = _CLUSTER_RE.search(body.lower())
        if cluster:
            return GooglevideoNode(error=f"redirector назвал кластер {cluster.group(1)}, а не узел sn-…")
        return GooglevideoNode(error="в ответе redirector нет узла sn-…")
    return GooglevideoNode(node=node, host=node_host(node))


def googlevideo_node_to_text(fetch: Fetcher | None = None) -> str:
    return resolve_googlevideo_node(fetch).to_text()


if __name__ == "__main__":  # pragma: no cover - CLI: python3 -m zap2_gui.adapters.googlevideo_node
    print(googlevideo_node_to_text())


__all__ = [
    "GooglevideoNode",
    "REDIRECTOR_HOST",
    "REPORT_MAPPING_URL",
    "googlevideo_node_to_text",
    "node_host",
    "parse_report_mapping",
    "resolve_googlevideo_node",
]
