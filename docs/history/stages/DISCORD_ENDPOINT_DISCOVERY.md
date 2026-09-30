# Обнаружение endpoint Discord

Статус: справка по Stage 7g–7x.

## Задача

Когда desktop Discord зависает на `Checking for updates`, нельзя бесконечно угадывать updater-домены. Сначала нужно посмотреть, какие TCP/UDP sockets открывает реальный процесс.

## Что делает watcher

Watcher периодически читает:

```text
ss -tunp
pgrep -af [Dd]iscord
```

и сохраняет видимые текущему пользователю process-owned endpoints.

Он не:

- запускает Discord;
- требует `sudo`;
- меняет firewall, hostlists или runtime state;
- захватывает payload;
- доказывает работоспособность стратегии.

Снимки хранятся в:

```text
.zap2/discord-discovery/
```

## Команды CLI

```bash
PYTHONPATH=gui python -m zap2_gui.app --discord-endpoint-plan
PYTHONPATH=gui python -m zap2_gui.app --discord-endpoint-watch --discord-endpoint-seconds 90
PYTHONPATH=gui python -m zap2_gui.app --discord-endpoint-report
```

Во время watch владелец запускает Discord и оставляет его на проблемном этапе.

## GUI

В `Диагностика -> Blockcheck lab` кнопка `Endpoints` показывает plan и последний отчёт. Длинный watcher остаётся CLI-first, чтобы GUI не зависал во время ручного запуска приложения.

## Интерпретация

- TCP 443: кандидаты updater/app/CDN.
- TCP 2053/2083/2087/2096/8443: возможные media/high TLS endpoints.
- UDP во время updater: признак, что путь не ограничивается TCP/TLS.
- Пустой отчёт: увеличить окно, проверить имя процесса или отдельно использовать privileged packet capture.

## Stage 7h: состояние socket

В watcher добавлены TCP state/timer и best-effort DNS mapping. Наблюдение `SYN-SENT` к Cloudflare edge означает, что отказ виден до полноценного TLS/HTTP. В таком случае новые TLS-only Blockcheck targets не являются первым приоритетом.

```bash
PYTHONPATH=gui python -m zap2_gui.app --discord-netlog-plan
```

Netlog не запускается автоматически, потому что Chromium netlog может содержать приватные URL, headers и token-like данные.

## Stage 7i: DNS edge

```bash
PYTHONPATH=gui python -m zap2_gui.app --discord-dns-edge-plan
PYTHONPATH=gui python -m zap2_gui.app --discord-dns-edge-check
```

Проверка сравнивает несколько resolvers и TCP 443 для полученных edge IP, не меняя системный DNS. Если все адреса дают timeout, проблема шире простой DNS-подмены.

## Stage 7x: HAR

HAR добавляет hostname-level evidence для web/API/gateway/CDN/upload. Анализатор сохраняет только sanitized summary без cookies, query strings, bodies и WebSocket payloads.

HAR не заменяет pre-TLS наблюдение: он видит только запросы, которые уже дошли до HTTP/WebSocket уровня.
