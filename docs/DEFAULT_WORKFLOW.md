# Основной workflow запуска и остановки

Stage 14 завершает цепочку `v0.3-alpha` для controlled runtime lifecycle: теперь дефолтную стратегию можно подготовить, подтвердить, запустить и отключить одной понятной парой команд.

Это не bootstrap и не installer. Workflow использует уже импортированное ядро, уже существующий `default` profile, стратегию `manual-local`, runtime state `.zap2/runtime`, owner confirmation gate и отдельные слои `apply/revert` + `session runner`.

## Предварительное условие: собранный nfqws2

`default-start` проверяет наличие исполняемого `core/zapret2/nfq2/nfqws2` до применения nftables-правил. Если бинарника нет, сначала выполните beta-stage build workflow:

```bash
PYTHONPATH=gui python -m zap2_gui.app --default-build-plan
PYTHONPATH=gui python -m zap2_gui.app --runtime-confirm runtime-default-manual-local-default-build-workflow-plan
PYTHONPATH=gui python -m zap2_gui.app --default-build --confirm runtime-default-manual-local-default-build-workflow-plan
```

После успешной сборки нужно заново выполнить `--default-start-plan` и `--runtime-confirm runtime-default-manual-local-default-start-workflow-plan`, потому что start preflight должен подтверждаться уже для состояния, где executable существует.

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
2. проверить дочерние plan hash для `runtime-start`, `owner-rules-apply` и аварийного `owner-rules-revert-on-start-failure`;
3. проверить наличие и исполняемость `core/zapret2/nfq2/nfqws2` до firewall apply;
4. создать derived confirmations для дочерних plans на основе подтверждённого composite plan;
5. применить owned nftables rules через Stage 12 apply layer;
6. запустить локальную `nfqws2` session через session runner;
7. если `nfqws2` завершился сразу после start, автоматически выполнить child revert для только что применённых owner-rules;
8. записать workflow state и runtime log.

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

## Beta-stage 3: sudo-owner UID/GID и аварийный rollback

При реальном запуске выяснилось, что `nfqws2` успешно стартует под `sudo`, читает hostlist, а затем upstream drop-root переводит процесс в UID/GID `2147483647`. Такой synthetic пользователь может потерять доступ к hostlist внутри пользовательского workspace, после чего процесс завершается с `file_open_test: Permission denied`.

Исправление `v0.3-beta_stage_3`:

- session runner при root/sudo запуске добавляет в args файл `--uid=<SUDO_UID>:<SUDO_GID>`;
- если `SUDO_UID/SUDO_GID` недоступны, используется владелец корня workspace, а затем root fallback;
- default start plan включает child plan `owner-rules-revert-on-start-failure`;
- если session падает после успешного nft apply, workflow выполняет revert owned table и возвращает состояние `failed-rolled-back`;
- CLI `--default-start` возвращает ненулевой код, если workflow не дошёл до состояния `started`.

## Что считать готовностью alpha-цепочки

После Stage 14 у проекта есть связанный путь:

```text
profiles/strategies -> runtime plan -> state/log/confirmation -> apply/revert -> session runner -> default start/stop
```

Это достаточная точка, чтобы закрыть `v0.3-alpha` и дальше переходить к `v0.3-beta`: улучшать GUI, диагностику, build status, UX подтверждений и устойчивость дефолтной стратегии.

## v0.3-beta Stage 4: Default strategy import и GUI runtime controls

Stage 4 переносит первую базовую стратегию из Windows GUI: `Default v1 (game filter)`. Перенос частичный и контролируемый: оригинальный Windows preset хранится как reference, а Linux runtime получает только seed hostlist и минимальные `nfqws2`-совместимые Lua-аргументы. Полный WinDivert preset не исполняется напрямую.

Также Stage 4 переносит CLI build/start/stop/status workflow во вкладку `Обзор` PyQt shell. GUI не запускает `sudo` и не применяет firewall скрыто: он готовит планы, подтверждает plan id через существующий confirmation gate и показывает owner-команды для терминала.
## GUI и privileged execution

CLI-команды `sudo ... --default-start/--default-stop` остаются ручным путём разработчика. В PyQt GUI тот же workflow запускается через `sudo -A`/SUDO_ASKPASS после сохранённого plan и confirmation. GUI не хранит пароль и не обходит `planHash`.
