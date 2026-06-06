# Runtime NFQUEUE policy

Начиная с `v0.3-beta_stage_14` default runtime больше не использует глобально фиксированную NFQUEUE `200`.

## Почему

Во время GUI single-button workflow старые экспериментальные процессы `nfqws2` могли оставаться привязанными к очереди `200` вне текущего `.zap2` state. Новый запуск тогда доходил до `nfq_create_queue()` и завершался с `Operation not permitted`/ошибкой привязки очереди, хотя build, hostlist, Lua inputs и nftables rollback уже работали корректно.

## Правило

Номер очереди выбирается детерминированно для пары `workspace root + profile id` в диапазоне `200..599`. Один resolver используется и для:

- nftables apply plan (`queue num <qnum> bypass`);
- session args `nfqws2` (`--qnum=<qnum>`);
- runtime state/diagnostics.

Для ручной диагностики можно задать:

```bash
ZAP2_NFQUEUE_NUM=321 PYTHONPATH=gui python -m zap2_gui.app --default-start-plan
```

Override должен использоваться только локально и осознанно.

## Ограничения

Это не заменяет stop/revert. Если где-то остался старый процесс `nfqws2`, его всё равно нужно обнаружить и корректно остановить. Но новый workspace больше не обязан конфликтовать с историческим номером `200`.
