# Классификатор ошибок запуска

Дата: 2026-06-29

## Цель

Overview должен показывать не только длинный log output, но и короткую причину, почему выбранный набор компонентов не стал `running`.

Для этого добавлен классификатор ошибок запуска и жёлтая dismissable-плашка в Overview.

## Плашка

Плашка содержит:

- стабильный код ошибки;
- короткое человеческое сообщение;
- icon-only кнопку копирования короткого текста;
- icon-only кнопку копирования полного текста;
- крестик закрытия.

Короткий текст имеет вид:

```text
Z2-LAUNCH-PARTIAL: Не все выбранные компоненты стали running после запуска.
```

Полный текст содержит код, severity, сообщение и подробный redacted output действия из `.zap2/runtime/logs/default.overview-action-output.log`.

## Коды

| Код | Значение |
| --- | --- |
| `Z2-LAUNCH-PARTIAL` | Комбинированный запуск завершился, но не все выбранные supported-компоненты стали `running`. |
| `Z2-LAUNCH-PLAN-ONLY` | План был подготовлен/подтверждён, но сам action ещё не был исполнен. |
| `Z2-ZAPRET-BINARY-MISSING` | Выбран Zapret default, но `core/zapret2/nfq2/nfqws2` отсутствует или не executable. Нужен build workflow. |
| `Z2-TUNNEL-PROFILE-MISSING` | Выбран VLESS tunnel, но активный VLESS profile отсутствует. |
| `Z2-TUNNEL-CORE-MISSING` | Выбран VLESS tunnel, но core binary не указан, не найден или не executable. |
| `Z2-TUNNEL-NOT-RUNNING` | Tunnel core не `running`, поэтому SOCKS route недоступен. |
| `Z2-TUNNEL-CORE-INCOMPATIBLE` | Выбранный core явно несовместим с transport профиля. |
| `Z2-TUNNEL-XHTTP-CORE` | Core stderr содержит `unknown transport protocol: xhttp`. |
| `Z2-TUNNEL-UPSTREAM-PREFLIGHT` | SOCKS поднят, но HTTPS через VLESS route не прошёл. |
| `Z2-PROBE-NFT-PERMISSION` | Probe не смог прочитать nft counters без нужных прав. |

## Где используется

Пока классификатор подключён к Overview action path. Он срабатывает на:

- exception во время action;
- успешный возврат action, после которого выбранный набор всё равно не стал `running`.

Подробности остаются во вкладке `Логи`, но причина становится видна сразу в Overview.
