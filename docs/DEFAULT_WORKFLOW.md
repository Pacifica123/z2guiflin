# Default start/stop workflow

Stage 14 завершает цепочку `v0.3-alpha` для controlled runtime lifecycle: теперь дефолтную стратегию можно подготовить, подтвердить, запустить и отключить одной понятной парой команд.

Это не bootstrap и не installer. Workflow использует уже импортированное ядро, уже существующий `default` profile, стратегию `manual-local`, runtime state `.zap2/runtime`, owner confirmation gate и отдельные слои `apply/revert` + `session runner`.

## Команды владельца

Подготовить запуск:

```bash
PYTHONPATH=gui python -m zap2_gui.app --default-start-plan
```

Подтвердить конкретный composite plan:

```bash
PYTHONPATH=gui python -m zap2_gui.app --runtime-confirm runtime-default-manual-local-default-start-workflow-plan
```

Запустить дефолтную стратегию:

```bash
sudo PYTHONPATH=gui python -m zap2_gui.app --default-start --confirm runtime-default-manual-local-default-start-workflow-plan
```

Подготовить отключение:

```bash
PYTHONPATH=gui python -m zap2_gui.app --default-stop-plan
```

Подтвердить отключение:

```bash
PYTHONPATH=gui python -m zap2_gui.app --runtime-confirm runtime-default-manual-local-default-stop-workflow-plan
```

Отключить дефолтную стратегию:

```bash
sudo PYTHONPATH=gui python -m zap2_gui.app --default-stop --confirm runtime-default-manual-local-default-stop-workflow-plan
```

Журнал можно читать так:

```bash
PYTHONPATH=gui python -m zap2_gui.app --runtime-log --profile default
```

## Что делает default-start

`default-start` исполняет только подтверждённый composite plan и заново сверяет его `planHash`.

Порядок действий:

1. проверить `default` profile и стратегию `manual-local`;
2. проверить дочерние plan hash для `runtime-start` и `owner-rules-apply`;
3. проверить наличие и исполняемость `core/zapret2/nfq2/nfqws2` до firewall apply;
4. создать derived confirmations для дочерних plans на основе подтверждённого composite plan;
5. применить owned nftables rules через Stage 12 apply layer;
6. запустить локальную `nfqws2` session через Stage 11 session runner;
7. записать workflow state и runtime log.

## Что делает default-stop

`default-stop` тоже требует composite plan confirmation.

Порядок действий:

1. прочитать runtime/session state;
2. попытаться остановить только наш PID с marker `zap2-runtime-session-v1`;
3. выполнить Stage 12 revert для owned nftables table;
4. записать workflow state и runtime log;
5. не трогать чужие процессы, чужие firewall rules и service mode.

## Границы безопасности

Stage 14 намеренно не делает следующее:

- не вызывает `install_easy.sh`, `install_bin.sh`, `uninstall_easy.sh` или другие upstream installer scripts;
- не делает remote bootstrap через `curl`/`wget`;
- не собирает ядро автоматически;
- не включает systemd service mode;
- не делает `systemctl enable` или `systemctl start`;
- не скрывает privileged действия за GUI-магию;
- не исполняет реальный `nft` в devctl-проверках.

Автоматические проверки используют fake `nfqws2` и fake runner для nft-команд. Реальный запуск `default-start/default-stop` остаётся локальным действием владельца и требует осознанного `sudo`.

## Что считать готовностью alpha-цепочки

После Stage 14 у проекта есть связанный путь:

```text
profiles/strategies -> runtime plan -> state/log/confirmation -> apply/revert -> session runner -> default start/stop
```

Это достаточная точка, чтобы закрыть `v0.3-alpha` и дальше переходить к `v0.3-beta`: улучшать GUI, диагностику, build status, UX подтверждений и устойчивость дефолтной стратегии.
