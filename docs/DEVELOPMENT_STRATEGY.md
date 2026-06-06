# Стратегия разработки — v0.3-alpha: перезапуск с нативным ядром

## Решение

Старая линия Zapret2GUIfLin закрыта как активная implementation baseline. Её архив остаётся полезным как тетрадь черновиков: там есть UI-эксперименты, заметки о privilege boundary, lifecycle-идеи, тесты и терминология. Новый продукт начинается с `v0.3-alpha`: чистая структура репозитория, vendored upstream-ядро и зафиксированное направление GUI на PyQt.

## Почему мы перезапускаемся

Предыдущая цепочка потратила слишком много патчей на попытку безопасно обернуть установку и обновление. Это тормозило разработку, потому что продукт постоянно вращался вокруг remote installation, shell orchestration и системных side effects. Новое направление снимает это давление: исходники ядра лежат внутри проекта, а GUI строится вокруг известного локального дерева.

Это **не** означает, что ассистент должен запускать привилегированные команды. Это означает, что ассистент не должен прятать необходимые действия разработчика за чрезмерно защитными абстракциями. Корректная граница такая:

- ассистент пишет патчи, документацию, адаптеры, планы и проверки;
- проверки являются read-only, если для конкретного патча явно не задан другой безопасный scope;
- владелец/разработчик может запускать привилегированные команды локально, потому что до `v1-stable` продукт гарантированно single-user;
- любая будущая привилегированная операция должна быть документированной, видимой и достаточно обратимой, чтобы владелец мог осознанно принять ответственность.

## Решение по GUI-фреймворку

Linux GUI будет построен на **PyQt**. В этом проекте “PyQt” по умолчанию означает линейку PyQt 6, если более поздний decision record не сузит или не пересмотрит этот выбор. Цель — использовать Qt widgets как основную desktop shell для вкладок, форм, логов, диагностики, настроек и будущих диалогов подтверждения.

Это решение о фреймворке, а не dependency-install patch. PyQt должен стать зависимостью приложения в момент появления первой настоящей GUI shell, а не на документационной стадии. Не заменять планируемую оболочку на PySide, GTK, Tkinter, web UI или terminal UI без явного решения владельца.

Начиная со Stage 5, PyQt6 фиксируется как optional dependency `gui`, потому что появляется первый GUI shell skeleton. Это не означает, что devctl-проверки должны устанавливать Qt или запускать окно: проверки остаются headless-safe и валидируют только структуру, pure Python модели и guarded imports.

## Правило языка документации

Вся наша проектная документация с этого этапа ведётся на русском языке. Это правило распространяется на:

- `README.md` в корне проекта;
- `core/README.md` и `gui/README.md`;
- все файлы в `docs/`;
- наши служебные заметки вроде `core/zapret2/UPSTREAM_IMPORT.md`.

Исключения допустимы для имён файлов, команд, API/CLI-идентификаторов, названий upstream-проектов, коротких технических терминов, цитат и неизменяемой upstream-документации внутри `core/zapret2/docs/`. Если будущий патч добавляет или меняет проектную документацию, он должен писать её по-русски и не возвращать активные docs к англоязычной базе.

## Глобальная цель серии v0.3

Построить Linux-first GUI, который считает `core/zapret2/` нативным исходным ядром и даёт владельцу-разработчику контролируемый workflow вокруг него:

1. инспектировать vendored-ядро и показывать, что в нём есть;
2. собирать ядро локально из исходников репозитория;
3. открывать конфигурацию стратегий/профилей, не пряча файлы от разработчика;
4. давать read-only диагностику и blockcheck-style discovery;
5. генерировать явные run/apply plans для действий, которым нужны привилегии;
6. только после этого вводить service/session management как слой, подтверждаемый владельцем.

Эта цель намеренно слишком крупная для одного-двух патчей. Нужна последовательность стадий `v0.3-alpha`, прежде чем проект можно будет переводить в `v0.3-beta`.

## Workflow патчей

Дальнейшие изменения продолжают идти через devctl zip patches:

```text
manifest.json
files/...
PATCH_SUMMARY.md
```

Имена патчей должны следовать stage-последовательности с версией:

```text
2026-06-06-v0.3-alpha_stage_1-native-core-reboot.devctl.patch.zip
2026-06-06-v0.3-alpha_stage_2-...
```

Патч должен включать:

- краткую продуктовую причину;
- source-alignment note, если он трогает ядро или reference behavior;
- проверки, которые не создают bytecode artifacts за пределами ожиданий devctl cleanup;
- отсутствие сетевой зависимости, если она явно не одобрена для конкретного патча;
- отсутствие `sudo`, service mutation и firewall mutation в автоматических проверках;
- русскоязычную проектную документацию, если патч меняет или добавляет docs.

## Граница ассистента и разработчика

Ассистент не должен пытаться запускать `sudo`, устанавливать пакеты, управлять сервисами, менять firewall rules или выполнять upstream installer scripts в своей среде. Эти операции либо невозможны в sandbox, либо не подходят для автоматической валидации патча.

Владелец может запускать такие команды локально, когда они являются частью задуманного продукта, потому что до `v1-stable` единственный гарантированный пользователь одновременно является разработчиком. Поэтому продукт должен оптимизироваться под прозрачный контроль, а не под патерналистское блокирование. Безопасность здесь означает понятное владение, dry-run capability, логи и видимость команд, а не бесконечный отказ моделировать workflow.

## Предпочтительная архитектура

```text
core/zapret2/       upstream-исходники ядра, импортируемые и ревьюируемые как source
gui/zap2_gui/      Python GUI shell на PyQt и orchestration приложения
profiles/          workspace-профили владельца и локальные hostlists
strategies/        каталог plan-only стратегий приложения
docs/              стратегия, reference notes и decision records
tools/             read-only проверки репозитория и будущие developer helpers
tests/             structural/unit tests для нашего слоя
```

GUI должен зависеть внутрь через узкие adapters, а не через случайные shell snippets. Будущие adapters должны сначала представлять операции как данные:

```text
inspect -> plan -> present -> owner confirms -> execute locally -> record result
```

## Ближайший план стадий

### v0.3-alpha_stage_1 — bootstrap

Создать чистое дерево проекта, импортировать исходники ядра, задокументировать новые правила и сохранить идеи Windows GUI как reference notes.

### v0.3-alpha_stage_2 — решение по GUI-фреймворку

Зафиксировать PyQt как выбранный фреймворк Linux GUI и не добавлять runtime-зависимость до появления настоящей GUI shell.

### v0.3-alpha_stage_3 — русификация документации

Перевести активную проектную документацию на русский и закрепить правило, что будущие изменения документации тоже пишутся на русском.

### v0.3-alpha_stage_4 — инвентаризация ядра и build map

Добавить read-only inventory model для Makefiles, C sources, Lua scripts, configs, service templates и docs. Сформировать machine-readable build map для `nfqws2`, `ip2net`, `mdig`, но не запускать сборку, privileged install, service management или firewall mutation. Результат этапа должен стать основой для будущего GUI-экрана Core и будущего local build adapter.

### v0.3-alpha_stage_5 — скелет GUI shell

Создать начальную PyQt Linux GUI shell с navigation placeholders: `Обзор`, `Ядро`, `Стратегии`, `Диагностика`, `Настройки`, `Логи`. Shell должна импортироваться без установленного PyQt6, а настоящий запуск окна должен оставаться локальной командой владельца.

### v0.3-alpha_stage_6 — local build adapter

Добавить local build adapter для ядра: `gui/zap2_gui/adapters/local_build.py` строит явные планы `make`-сборки по `BUILD_MAP.json`, показывает ожидаемые артефакты и остаётся plan-only в автоматических проверках. Проверки валидируют команды, цели и запреты на `sudo`/service/firewall mutation, но реальные host dependencies и запуск `make` остаются под контролем владельца.

### v0.3-alpha_stage_7 — workspace профилей/стратегий

Представить `profiles/` и `strategies/` как read-only project/user data. Взять из Windows GUI философию “toolbox/apothecary”, но не копировать Windows-specific service assumptions. Результат Stage 7: JSON-профили, strategy catalog, CLI `--list-profiles`/`--list-strategies`, вкладка `Стратегии` со статусом `profiles-backed` и проверки, которые валидируют связи, но ничего не применяют к системе.

### v0.3-alpha_stage_8 — runtime lifecycle contracts

Ввести язык runtime lifecycle как plan-only контракт: `run`, `apply`, `session`, `service`, runtime events, confirmation contract и rollback notes. Stage 8 валидирует структуры и safety-инварианты, но не запускает процессы, не применяет правила, не управляет service mode и не смешивает runtime с bootstrap.

### v0.3-alpha_stage_9+ — controlled runtime plan generation/execution

Следующая серия должна постепенно вывести default strategy к запуску и отключению: сначала generator start/stop/status plans, затем state dir/logs/confirmation gate, затем session runner, затем owner-confirmed apply/revert, затем service plans и только после этого default start/stop workflow.

## Definition of done для v0.3-beta

`v0.3-beta` можно рассматривать только тогда, когда у проекта есть рабочий GUI skeleton, локальный core build path, видимое управление strategies/profiles, диагностика и явный owner-confirmed путь для любой привилегированной операции. Beta не обязана иметь multi-user polish.

## Решение Stage 6: local build adapter

Начиная со Stage 6, сборка ядра моделируется как структурированный план, а не как немедленный запуск shell-команды. Adapter принимает target `all`, `nfqws2`, `ip2net`, `mdig` или `clean`, берёт данные из `BUILD_MAP.json` и возвращает:

- рабочую директорию команды;
- `argv` без склеивания в небезопасную shell-строку;
- ожидаемые артефакты;
- подсказки по локальным библиотекам;
- явные флаги, что автоматические проверки не должны выполнять этот план.

Это первый шаг к нормальному экрану `Ядро`: GUI сможет показывать пользователю понятную локальную сборку, а будущий runner будет добавлен отдельно и только после подтверждений.


## Решение Stage 7: workspace-профили и стратегии

Начиная со Stage 7, пользовательский workflow описывается отдельными данными проекта:

- `profiles/` хранит workspace-профили владельца, локальные hostlists и примеры профилей;
- `strategies/` хранит каталог plan-only стратегий;
- `gui/zap2_gui/adapters/workspace_profiles.py` читает эти данные и валидирует связи между профилем, стратегией и build target.

Это важный архитектурный шаг: GUI больше не должен думать о “стратегии” как о наборе случайных shell-команд. Сначала есть структурированные данные, затем экран просмотра, затем редактор, затем dry-run/apply plan и только потом owner-confirmed execution. Stage 7 не запускает `sudo`, не мутирует firewall, не управляет `systemd` и не выполняет стратегии автоматически.

Стратегия `manual-local` считается основной для одиночной разработки до `v1-stable`. Она следует философии `toolbox/apothecary`: приложение должно давать владельцу понятные инструменты, рецепты и планы, а не скрывать происходящее внутри install wizard.


## Решение Stage 8: runtime lifecycle contracts

Начиная со Stage 8, runtime lifecycle описывается отдельным top-level слоем `runtime/` и pure Python моделями в `gui/zap2_gui/models/`. Смысл этапа — зафиксировать язык будущих действий до появления executor:

- `run plan` описывает общее намерение `start`/`stop`/`status`;
- `apply plan` описывает будущие системные изменения отдельно от запуска процесса;
- `session plan` описывает lifecycle локального процесса;
- `service plan` описывает service mode отдельно от session mode;
- `confirmation` связывает разрешение владельца с конкретным plan hash;
- `runtime event` задаёт формат будущего журнала;
- `rollback notes` обязательны до исполнения.

Stage 8 намеренно не исполняет планы. Проверки читают схемы и examples, валидируют, что `automaticChecksMayExecute=false`, `bootstrapMixedIn=false`, `containsRemoteBootstrap=false`, `containsUpstreamInstallerScript=false`, и показывают CLI-сводку через `--runtime-contracts`. Это первый кирпич цепочки, которая позже должна привести к управляемому запуску и отключению default strategy.


## Stage 9: default strategy runtime plan generator

Stage 9 развивает Stage 8 без перехода к исполнению. Теперь проект умеет строить конкретный plan-only runtime view для `default/manual-local`: `start`, `stop` и `status`. В плане видны профиль, стратегия, build target, бинарник, hostlist, required artifacts, будущие session/log files, apply steps и rollback notes.

Это сознательно не `6b` и не build status model. Stage 9 продолжает записанную очередь controlled runtime lifecycle: сначала планы, затем state/log/confirmation, затем session runner, затем owner-confirmed apply/revert.


## Stage 10: runtime state, logs и confirmation gate

Stage 10 продолжает controlled runtime lifecycle после generator. Теперь plan-only результат можно сохранить в `.zap2/runtime/plans/`, снабдить стабильным `planHash`, записать rollback notes в `.zap2/runtime/rollback/`, создать owner confirmation в `.zap2/runtime/confirmations/` и вести append-only журнал `.zap2/runtime/logs/`.

Это первая разрешённая мутация в серии runtime lifecycle, но она ограничена workspace-директорией проекта. Stage 10 не запускает процесс, не вызывает `sudo`, не применяет системные правила и не управляет service mode. Смысл этапа — сделать будущий executor проверяемым: нельзя будет подтвердить один plan, а исполнить другой без расхождения hash.


## Stage 11: runtime session runner

Stage 11 впервые добавляет исполняемый runtime-компонент, но его область намеренно узкая: только lifecycle локального процесса `nfqws2`, только после prepared start-plan и owner confirmation, только с записью PID/state/log в `.zap2/runtime`. Runner не применяет системные правила, не управляет service mode и не смешивает процесс с bootstrap.

Ключевая граница этапа: `start` может создать процесс, `status` может прочитать session state, `stop` может остановить только PID с нашим marker. Firewall/routing apply, privileged revert и service plans остаются следующими отдельными stages.


## Stage 12: owner-confirmed apply/revert plan

Stage 12 впервые добавляет controlled privileged apply/revert, но не смешивает его с bootstrap и не прячет за session runner. Системные правила представлены отдельным adapter-слоем `runtime_apply.py`: сначала создаётся plan, затем он сохраняется в `.zap2/runtime/plans/`, получает `planHash`, подтверждается owner confirmation и только после этого может быть исполнен локальным владельцем через `sudo`.

Default backend Stage 12 — `nftables`: отдельная table `inet zap2_default`, отдельная chain `local_out`, NFQUEUE `200` для локального TCP 80/443 и UDP 443. Revert удаляет только owned table и не делает глобальный firewall reset. Это минимальная single-user схема для default strategy, а не универсальный router installer.

Devctl-проверки Stage 12 не вызывают настоящий `nft`, не требуют root и не меняют firewall. Они проверяют только структуру плана, hash/confirmation gate и fake-runner execution. Service mode остаётся будущим Stage 13.

## Stage 13: service plans

Stage 13 добавляет service mode, но не делает его дефолтным workflow. Теперь проект умеет подготавливать systemd-oriented plans для `install`, `start`, `stop` и `remove`, сохранять их в `.zap2/runtime`, привязывать подтверждение к `planHash` и выполнять guarded `install/remove` только после явного owner confirmation.

Service mode остаётся отдельным от session runner. Он не запускается автоматически, не включает автозапуск по умолчанию, не управляет nftables/firewall и не смешивается с bootstrap. Для одиночной разработки основной путь по-прежнему должен идти через controlled default workflow на базе session mode; service mode нужен как будущая опция, когда стратегия станет достаточно стабильной.

## Stage 14: default strategy start/stop workflow

Stage 14 завершает alpha-цепочку controlled runtime lifecycle. Теперь отдельные кирпичи Stage 9–13 собраны в один owner-confirmed workflow для дефолтной стратегии:

- `--default-start-plan` готовит composite plan для `default/manual-local`;
- `--default-start --confirm <plan-id>` после owner confirmation выполняет `apply owner-rules` и запускает `nfqws2` session;
- `--default-stop-plan` готовит composite plan отключения;
- `--default-stop --confirm <plan-id>` останавливает только нашу session и выполняет revert owned nftables table;
- workflow state, runtime log и rollback notes сохраняются в `.zap2/runtime`.

Stage 14 не смешивает runtime с bootstrap: upstream installer scripts, remote install, service mode и автозапуск не входят в default workflow. Devctl-проверки используют fake `nfqws2` и fake nft runner, поэтому не требуют root и не меняют систему.

## Следующая веха: v0.3-beta

После Stage 14 очередь `v0.3-alpha` считается закрытой. Следующие патчи должны идти уже как `v0.3-beta`, если не возникнет срочный hotfix к Stage 14.

Цель `v0.3-beta` — не переписывать заново runtime lifecycle, а превратить уже созданный controlled workflow в удобный продуктовый слой:

- экран GUI для default workflow и статусов;
- build status model и понятная диагностика отсутствующего `nfqws2`;
- UX подтверждений planHash/rollback notes;
- read-only просмотр runtime log;
- улучшение профилей/стратегий без смешивания с bootstrap;
- постепенное доведение default strategy до повседневного использования владельцем.


## v0.3-beta_stage_1: default build prerequisite

Первый beta-патч закрывает практический разрыв, обнаруженный при ручной проверке Stage 14: `default-start` корректно останавливался на отсутствии `nfqws2`, но не давал штатного owner-confirmed пути сборки. Теперь default strategy имеет явный preflight-порядок: сначала `--default-build-plan`, затем `--runtime-confirm`, затем `--default-build` без `sudo`, после чего нужно заново подготовить и подтвердить `--default-start-plan`.

Это не откат к installer-подходу. Build workflow использует только vendored-исходники, локальный `make`, runtime state/confirmation gate и логи `.zap2/runtime`. Он не скачивает код, не вызывает upstream installer scripts, не меняет firewall/service state и не исполняется devctl-проверками.


## v0.3-beta_stage_2 — build dependency preflight

После первого реального запуска `--default-build` выяснилось, что workflow корректно дошёл до локального `make`, но UX был недостаточным: при отсутствии `libnetfilter_queue` владелец видел compiler stderr вместо предварительной диагностики. Stage 2 beta добавляет `--default-build-deps` и встроенный preflight в `--default-build`.

Правило на будущее: если workflow зависит от системных пакетов, сначала должен появиться read-only preflight с owner action hints. Автоматически устанавливать пакеты, запускать `sudo apt/dnf/pacman/zypper` или upstream `install_prereq.sh` нельзя.


## v0.3-beta_stage_3 — sudo-owner runtime session fix

При первом реальном `default-start` после успешной сборки `nfqws2` процесс завершился сразу: stderr показал `file_open_test: Permission denied` и невозможность заново открыть `profiles/hostlists/default.hosts`. Причина: upstream `nfqws2` под root по умолчанию сбрасывает привилегии в UID/GID `2147483647`, который не обязан иметь доступ к пользовательскому workspace.

Stage 3 beta фиксирует это на уровне session runner: при запуске через `sudo` в args добавляется `--uid=<SUDO_UID>:<SUDO_GID>`, чтобы после открытия NFQUEUE процесс работал от имени владельца workspace и мог читать hostlist. Дополнительно default workflow получает аварийный child-revert: если owner-rules уже применены, но session старт падает, workflow выполняет revert owned nftables table и сохраняет state `failed-rolled-back`.

Правило на будущее: любой privileged runtime workflow должен учитывать post-root/drop-root доступ к workspace-файлам и иметь автоматический rollback для изменений, которые уже были применены в рамках подтверждённого composite plan.

## v0.3-beta Stage 4: Default strategy import и GUI runtime controls

Stage 4 переносит первую базовую стратегию из Windows GUI: `Default v1 (game filter)`. Перенос частичный и контролируемый: оригинальный Windows preset хранится как reference, а Linux runtime получает только seed hostlist и минимальные `nfqws2`-совместимые Lua-аргументы. Полный WinDivert preset не исполняется напрямую.

Также Stage 4 переносит CLI build/start/stop/status workflow во вкладку `Обзор` PyQt shell. GUI не запускает `sudo` и не применяет firewall скрыто: он готовит планы, подтверждает plan id через существующий confirmation gate и показывает owner-команды для терминала.

### v0.3-beta stage 5 — GUI polkit privilege bridge

Цель этапа: перенести privileged start/stop default workflow в PyQt GUI через системный графический запрос прав polkit (`pkexec`), не используя терминальный `sudo` после нажатия кнопки и не обходя runtime confirmation gate.

## v0.3-beta_stage_6 — GUI workflow ясность и stale-state диагностика

После появления polkit-кнопок нужно закрыть UX-разрыв между планированием и
исполнением. GUI обязан показывать не только `План сборки` и `Подтвердить
сборку`, но и явное действие `Собрать без sudo`. Privileged `Включить` не должен
вызывать `pkexec`, если `nfqws2` отсутствует или не исполняемый: сначала нужно
показать owner-facing инструкцию по build workflow.

Также runtime state нельзя считать актуальным, если `.zap2/runtime` был перенесён
из другого workspace. Session/status слой должен помечать такие записи как
`stale` и не останавливать PID из чужого workspace. Это важно для devctl-архивов
и пользовательских экспериментов, где проекты часто копируются между разными
папками.
