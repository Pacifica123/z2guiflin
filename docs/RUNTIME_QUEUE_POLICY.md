# Политика NFQUEUE для runtime

Начиная с `v0.3-beta_stage_14` default runtime больше не использует глобально фиксированную NFQUEUE `200`.

## Почему

Во время GUI single-button workflow старые экспериментальные процессы `nfqws2` могли оставаться привязанными к очереди `200` вне текущего `.zap2` state. Новый запуск тогда доходил до `nfq_create_queue()` и завершался с `Operation not permitted`/ошибкой привязки очереди, хотя build, hostlist, Lua inputs и nftables rollback уже работали корректно.

## Правило

Номер очереди выбирается детерминированно для общей runtime owner identity `desktop UID + canonical workspace digest + profile id` в диапазоне `200..599`. Один resolver используется и для:

- nftables apply plan (`queue num <qnum> bypass`);
- session args `nfqws2` (`--qnum=<qnum>`);
- runtime state/diagnostics.

Для ручной диагностики можно задать:

```bash
ZAP2_NFQUEUE_NUM=321 PYTHONPATH=gui python -m zap2_gui.app --default-start-plan
```

Override должен использоваться только локально и осознанно.

## Ограничения

Это не заменяет stop/revert. Перед firewall mutation runtime теперь делает read-only `/proc` scan и при положительном свидетельстве, что выбранный qnum уже занят другим `nfqws2`, останавливает start вместо случайного выбора новой очереди. Это сохраняет подтверждённую plan identity и не маскирует конфликт.

## v0.3-dev Stage 16 — queue scope и loop guard

NFQUEUE теперь используется не только с workspace-specific номером, но и с более
осторожным nftables фильтром. Apply-plan записывает UID владельца, выбранный из
`SUDO_UID`, текущего пользователя или владельца workspace, и добавляет
`meta skuid <uid>` в queue rule. Это важно для desktop-сценария: системные
процессы и NetworkManager connectivity checks не должны ломаться из-за
экспериментальной пользовательской strategy.

Вторая граница — `--fwmark=0x40000000`. Такой же mark используется в nft rule как
loop guard: пакеты, которые nfqws2 сгенерировал сам, не должны снова попадать в
ту же NFQUEUE. Это приближает минимальный GUI apply к upstream-рекомендации
«mark filter first, queue only what is needed».


## v0.3-dev Stage 17 — UID/hash stability

Во время GUI privileged start owner-rules executor больше не пересобирает
команды apply/revert из текущего root/sudo окружения. Он проверяет hash
сохранённого plan и confirmation, после чего исполняет сохранённый plan. Поэтому
`meta skuid <uid>` остаётся тем UID, который был показан и подтверждён на этапе
plan, даже если `sudo -A` не передал ожидаемые переменные окружения.
