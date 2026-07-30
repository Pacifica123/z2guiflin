# Discord SYN-data edge-flow v2b

Статус: историческая запись Stage 7v.

## Причина появления

После раннего варианта v2 socket Discord смог перейти из `SYN-SENT` в `ESTAB`, но загрузка `https://discordapp.com/app?...` завершалась timeout после TLS ClientHello.

Это показало новый уровень отказа:

```text
SYN-SENT -> ESTAB -> TLS ClientHello -> TLS ServerHello -> HTTP/
```

В наблюдении переход останавливался после ClientHello и проявлялся как `ERR_TIMED_OUT`.

## Стратегия

Был добавлен вариант:

```text
community-discord-syndata-edge-flow-v2b
```

Он сохранил ранние edge-IP ветки v2 и расширил host coverage:

```text
discordapp.com
www.discordapp.com
```

## Назначение

Вариант проверял, является ли timeout следствием отсутствующего webapp host в hostlist. Если после добавления доменов поток всё равно останавливается после ClientHello, проблема не сводится к host coverage.

## Проверка

```bash
PYTHONPATH=gui python -m zap2_gui.app --select-strategy community-discord-syndata-edge-flow-v2b
PYTHONPATH=gui python -m zap2_gui.app --show-strategy community-discord-syndata-edge-flow-v2b
```

После owner-confirmed запуска сравниваются endpoint state, TLS progress и содержимое `.zap2/runtime/sessions/default.nfqws2.args`.
