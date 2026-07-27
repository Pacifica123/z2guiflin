# Discord HAR discovery — v0.4-alpha Stage 7x

Этот stage добавляет безопасный разбор browser HAR для Discord. Цель не в том,
чтобы вытащить из HAR секреты или повторить запросы. Цель уже: получить короткую
карту фактических web-hosts, HTTP/WebSocket статусов и path-шаблонов, а затем
сравнить её с `discord-desktop` preset и `profiles/hostlists/default.hosts`.

## Что анализатор читает

Команда принимает обычный `.har` или `.zip`, внутри которого есть `.har`:

```bash
PYTHONPATH=gui python -m zap2_gui.app --discord-har-plan
PYTHONPATH=gui python -m zap2_gui.app --discord-har-analyze /path/to/discord.har.zip
PYTHONPATH=gui python -m zap2_gui.app --discord-har-report
```

Файл читается локально. Сеть, `sudo`, nftables, systemd, hostlist и runtime state
не меняются. Результат сохраняется в `.zap2/discord-discovery/har-summary-*.json`.

## Что намеренно выбрасывается

Raw HAR почти всегда приватный. В нём могут быть `Authorization`, cookies,
`x-super-properties`, pre-signed upload URLs, query-параметры, request bodies,
response bodies и WebSocket payloads. Поэтому анализатор сохраняет только:

- имя host;
- категорию host;
- количество запросов;
- методы;
- коды ответов;
- redacted path-шаблоны без query string;
- факт WebSocket/HTTP 101;
- имена sensitive headers, но не их значения;
- число уникальных `serverIPAddress`, но не сами IP.

Длинные snowflake/id/token-like части path заменяются на `{id}` или `{token}`.
Это нужно, чтобы в отчёт не попали user id, channel id, attachment signatures и
похожие значения.

## Категории

Отчёт группирует hosts по понятным зонам:

| Категория | Смысл |
| --- | --- |
| `app-api` | основной `discord.com` API/app слой |
| `gateway` | WebSocket gateway `gateway.discord.gg` |
| `updater` | updater/bootstrap targets |
| `cdn-media` | CDN, avatars, attachments preview, image proxy |
| `media-relay` | динамические `*.discord.media` hosts |
| `attachment-upload` | pre-signed upload hosts на Google Storage |
| `status` | support/status API |
| `external-discord-support` | Discord-related host вне основной цепочки |
| `external-other` | не-Discord host, оставлен только как агрегат |

## Как применять результат

HAR useful для discovery и отчётности. Он помогает увидеть, например, что web
Discord использовал `images-ext-1.discordapp.net`, `gateway.discord.gg`,
`c-hel*.discord.media` или `discord-attachments-uploads-prd.storage.googleapis.com`.
Но HAR не доказывает, что конкретная `nfqws2` desync strategy работает: браузер
уже прошёл до HTTP/WebSocket уровня, а текущий blocker проекта может находиться
раньше, на `TCP ESTAB → TLS ClientHello → no ServerHello`.

Поэтому правило stage такое:

1. Missing host из HAR сначала считается discovery/report кандидатом.
2. Runtime hostlist или service target preset меняются только после owner review.
3. Third-party upload hosts вроде `*.storage.googleapis.com` нельзя слепо расширять
   до всего `storage.googleapis.com` без отдельного решения.
4. Dynamic `*.discord.media` нужно проверять suffix coverage, а не добавлять один
   конкретный сгенерированный host.

## Связь с endpoint discovery

`--discord-endpoint-watch` смотрит локальные sockets процесса Discord: IP, state,
timer, SYN-SENT/ESTAB. `--discord-har-analyze` смотрит browser HAR: host, path,
status и WebSocket факт. Это разные уровни. Сильный отчёт для следующего патча
сравнивает оба источника, но не смешивает их в одну автоматическую стратегию.

## v0.4-alpha Stage 8d — HAR workbench

Stage 8d добавляет второй слой поверх sanitized summary:

```bash
PYTHONPATH=gui python -m zap2_gui.app --discord-har-workbench /path/to/discord.har
PYTHONPATH=gui python -m zap2_gui.app --discord-har-workbench-report
PYTHONPATH=gui python -m zap2_gui.app --discord-har-group-plan har-tls-problems
```

Workbench автоматически выполняет безопасную часть цепочки:

```text
HAR import
  -> redaction
  -> host/status/error evidence
  -> группы HTTP, TLS, WebSocket, HTTP/3
  -> targets.txt + blockcheck-options.json для каждой группы
  -> preset-blueprint.json
```

В summary теперь сохраняются только обезличенные признаки ошибки и протокола:
`schemes`, `httpVersions`, `l7Hints`, `transportHints`, количество failed status и
категории ошибок вроде `dns`, `timeout`, `tls`, `reset-or-closed`. Исходный текст
ошибки не сохраняется.

Определение транспорта имеет уровни уверенности:

- `http`, `https`, `ws`, `wss` дают уверенный browser-level признак TCP;
- `HTTP/3`, `h3` или явный QUIC marker дают признак UDP/443;
- отсутствие этих полей не позволяет угадать транспорт;
- STUN, RTP, SRTP и Discord Voice media-flow из HAR не определяются.

Workbench не запускает Blockcheck. Он только подставляет одну группу в custom
Blockcheck plan. Привилегированный run остаётся отдельным owner-confirmed
действием. Итоговый executable preset не формируется, пока для каждого
обязательного host группы не выбрана подтверждённая стратегия.

Файлы workbench хранятся в `.zap2/discovery/har-workbench-*`; raw HAR туда не
копируется.
