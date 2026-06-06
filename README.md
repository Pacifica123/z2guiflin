# Zap2 GUI Linux — v0.3-alpha: перезапуск с нативным ядром

Этот репозиторий — новая продуктовая линия Linux GUI вокруг vendored-копии `zapret2` от bol-van. Предыдущий проект Zapret2GUIfLin больше не считается активной архитектурной базой: он используется только как тетрадь черновиков, тестов, UX-экспериментов и продуктовых заметок.

## Что изменилось в v0.3-alpha

`v0.3-alpha` начинается с чистой структуры:

```text
core/      исходники vendored-ядра и метаданные импорта
gui/       наш Python-пакет будущего GUI на PyQt
docs/      стратегия продукта, справочные заметки и правила разработки
profiles/  workspace-профили владельца и локальные hostlists
strategies/ каталог plan-only стратегий
runtime/   контракты будущего runtime lifecycle
tools/     проверки репозитория без сети, sudo и управления сервисами
tests/     небольшие структурные тесты для новой базы
```

Ключевые архитектурные решения: upstream-ядро является частью исходного дерева репозитория, Linux GUI строится на PyQt, а документация проекта ведётся на русском языке. Приложение не должно самозагружаться через удалённые `curl`-сценарии или непрозрачные installer scripts. Будущие привилегированные операции должны оформляться как явные, обозримые планы, которые запускает владелец проекта на своей машине.

## Текущий статус

Это ранняя `v0.3-alpha` база, а не готовое приложение для конечного пользователя. Она импортирует upstream-исходники в `core/zapret2/`, создаёт минимальный GUI-пакет в `gui/zap2_gui/`, фиксирует PyQt как выбранный GUI-фреймворк, русифицирует проектную документацию, добавляет read-only инвентаризацию ядра с build map, вводит первый скелет PyQt GUI shell, добавляет local build adapter для явных планов локальной сборки и вводит workspace-профили/стратегии как read-only project data, добавляет runtime lifecycle contracts как plan-only фундамент будущего запуска/отключения, генерирует default strategy runtime plans для `start`, `stop`, `status`, вводит runtime state/confirmation gate, добавляет guarded session runner для процесса `nfqws2` и вводит owner-confirmed apply/revert plan для nftables-правил.

```bash
python tools/check_project_tree.py
python tools/inventory_core.py --check
python -m compileall -q gui tools tests
python -m zap2_gui.app
python -m zap2_gui.app --build-plan
python -m zap2_gui.app --list-profiles
python -m zap2_gui.app --list-strategies
python -m zap2_gui.app --runtime-contracts
python -m zap2_gui.app --validate-runtime-contracts
python -m zap2_gui.app --runtime-plan start --profile default
python -m zap2_gui.app --runtime-plan stop --profile default
python -m zap2_gui.app --runtime-plan status --profile default
python -m zap2_gui.app --runtime-prepare start --profile default
python -m zap2_gui.app --runtime-confirm runtime-default-manual-local-start-plan
python -m zap2_gui.app --runtime-session-status --profile default
```

Эти проверки намеренно read-only. Они сверяют структуру, документацию, snapshot-инвентаризацию, build map, local build plan и импортируемость GUI shell, но не собирают C-ядро, не устанавливают пакеты, не запускают окно, не трогают firewall/service state и не требуют повышенных привилегий. Настоящий запуск окна выполняется отдельно через `python -m zap2_gui.app --gui` на машине владельца с установленным PyQt6. Просмотр плана локальной сборки доступен через `python -m zap2_gui.app --build-plan`: команда показывает `make`-план, но не выполняет его. Просмотр workspace-профилей и стратегий доступен через `--list-profiles`, `--show-profile`, `--list-strategies` и `--show-strategy`; эти команды только читают JSON-данные. Просмотр и валидация runtime lifecycle contracts доступны через `--runtime-contracts` и `--validate-runtime-contracts`; они фиксируют язык будущих run/apply/session/service plans, но ничего не запускают. Генератор Stage 9 доступен через `--runtime-plan start|stop|status --profile default`: он показывает profile, strategy, build target, binary, hostlist, session/log files, apply steps и rollback notes, но также ничего не исполняет. Stage 12 добавляет `--runtime-apply-plan`, `--runtime-revert-plan`, `--runtime-apply --confirm <plan-id>` и `--runtime-revert --confirm <plan-id>`: plan-команды безопасны и не исполняются, а реальные apply/revert предназначены только для локального owner-confirmed запуска через `sudo`.

## Правило разработки

Все дальнейшие изменения должны приходить через архивы devctl-патчей. Ассистент готовит патчи, документацию, адаптеры и проверки; владелец/разработчик решает, когда запускать локальные привилегированные команды на своей машине.

Вся наша проектная документация должна быть на русском языке. Исключения: имена файлов, идентификаторы, названия upstream-проектов, команды, технические термины вроде `PyQt`, `systemd`, `sudo`, а также неизменяемая upstream-документация внутри `core/zapret2/`.


## Runtime state и confirmation gate

Начиная со Stage 10, проект умеет создавать локальный runtime state store в `.zap2/runtime/`. Это workspace-only слой: он сохраняет prepared runtime plan, считает `planHash`, пишет rollback notes, создаёт confirmation record и ведёт JSONL-журнал. Он не запускает `nfqws2`, не применяет firewall rules, не управляет сервисами и не требует `sudo`.

```bash
python -m zap2_gui.app --runtime-prepare start --profile default
python -m zap2_gui.app --runtime-confirm runtime-default-manual-local-start-plan
python -m zap2_gui.app --runtime-log --profile default
```

Эти команды являются подготовкой будущего controlled runtime lifecycle. Они дают проверяемую связь `plan id -> plan hash -> confirmation -> rollback notes -> log`, но не исполняют сам plan.


## Runtime session runner

Начиная со Stage 11, проект умеет управлять lifecycle локального процесса `nfqws2` как workspace session. Команды `--runtime-session-start`, `--runtime-session-status` и `--runtime-session-stop` используют `.zap2/runtime`, требуют подготовленный и подтверждённый start-plan и останавливают только PID, записанный нашим session marker.

Этот слой не применяет firewall/routing rules, не создаёт systemd service, не запускает bootstrap и не вызывает upstream installer scripts. Сам запуск процесса ещё не равен полноценной работе стратегии: направление трафика в NFQUEUE появится только в будущих owner-confirmed apply/revert stages.

## Stage 13: service plans

В проект добавлен отдельный service mode для будущего systemd-сценария. Он не заменяет session runner и не становится дефолтным запуском. Команды Stage 13:

```bash
PYTHONPATH=gui python -m zap2_gui.app --service-plan install --profile default
PYTHONPATH=gui python -m zap2_gui.app --service-plan start --profile default
PYTHONPATH=gui python -m zap2_gui.app --service-plan stop --profile default
PYTHONPATH=gui python -m zap2_gui.app --service-plan remove --profile default
```

Guarded execution есть только для `install/remove` и требует `--runtime-confirm` плюс локальный owner-controlled запуск. Проверки проекта не вызывают настоящий `systemctl`.
