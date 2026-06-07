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

## Stage 15: синхронизация nft ports со strategy

Лог после Stage 14 показал новый класс проблемы: process мог быть живым, но default strategy не давала полезного результата, а desktop-сеть выглядела частично сломанной. Главный риск в старом apply-plan: nftables всегда отправлял UDP/443 в NFQUEUE, хотя текущая `manual-local` strategy не передавала `--filter-udp` и UDP-desync параметры в `nfqws2`.

Начиная со Stage 15 apply-plan строит nft queue rules из runtime args текущей strategy:

- `--filter-tcp=80,443` создаёт TCP queue rule;
- `--filter-udp=...` создаёт UDP queue rule;
- если UDP-фильтра нет, UDP/443 не перехватывается автоматически.

Это оставляет QUIC/UDP в обычном сетевом пути до тех пор, пока проект явно не добавит отдельную UDP/QUIC strategy. Так проще отличать «nfqws2 работает, но TCP-стратегия не помогает YouTube» от «мы сломали UDP-путь самим interception rule».
