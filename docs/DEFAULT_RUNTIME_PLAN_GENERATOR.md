# Default strategy runtime plan generator

Stage 9 добавляет генератор runtime plan для связки `profiles/default.json` + `strategies/manual-local.json`. Это следующий слой после runtime contracts: Stage 8 ввёл язык договоров, а Stage 9 научился строить конкретные планы `start`, `stop` и `status` из уже существующих данных проекта.

## Что генерируется

Команда:

```bash
PYTHONPATH=gui python -m zap2_gui.app --runtime-plan start --profile default
PYTHONPATH=gui python -m zap2_gui.app --runtime-plan stop --profile default
PYTHONPATH=gui python -m zap2_gui.app --runtime-plan status --profile default
```

План показывает:

- `profile` и `strategy`;
- `build target` из workspace-профиля;
- ожидаемый локальный бинарник `core/zapret2/nfq2/nfqws2`;
- hostlist `profiles/hostlists/default.hosts`;
- требуемые build artifacts и их read-only статус `exists/missing`;
- будущие session files в `.zap2/runtime/sessions/`;
- будущие plan/log/rollback files в `.zap2/runtime/`;
- apply steps с флагами `requires sudo` и `mutates system`;
- rollback notes до исполнения.

## Граница Stage 9

Stage 9 остаётся plan-only. Он не запускает `nfqws2`, не вызывает `make`, не создаёт `.zap2/`, не пишет runtime state, не вызывает `sudo`, не меняет firewall/routing и не управляет `systemd`.

Даже если в плане указано `requires sudo for apply: yes`, это описание будущего owner-confirmed apply/revert из следующих стадий. Сам генератор выполняет только чтение файлов проекта и проверку наличия ожидаемых артефактов через `stat`.

## Почему это важно

До этого у проекта были отдельные кирпичи: inventory, build map, local build adapter, profiles, strategies и runtime contracts. Stage 9 связывает их в первый практически полезный runtime view:

```text
profile -> strategy -> build target -> binary -> hostlist -> run/apply/session/service plan
```

Это ещё не запуск, но уже не абстрактная документация. GUI сможет показывать владельцу конкретный план запуска, остановки или статуса дефолтной стратегии без скрытых shell-команд.

## Что пойдёт дальше

Следующий слой должен добавить state dir, логи и confirmation gate. После него можно будет сохранять plan id, hash и owner confirmation так, чтобы нельзя было подтвердить один план, а исполнить другой.
