# Zap2 GUI Linux — v0.4-alpha: Discord desktop cycle

Этот репозиторий — новая продуктовая линия Linux GUI вокруг vendored-копии `zapret2` от bol-van. Предыдущий проект Zapret2GUIfLin больше не считается активной архитектурной базой: он используется только как тетрадь черновиков, тестов, UX-экспериментов и продуктовых заметок.

## Что изменилось в v0.3-alpha/v0.3-beta/v0.3-stable и почему теперь v0.4-alpha

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

`v0.3-stable` зафиксирована владельцем как первая практически полезная пользовательская цепочка: GUI умеет собрать prerequisites для vendored `zapret2`, реально прогнать Blockcheck lab по базовым доменным именам, найти `AVAILABLE` стратегии, экспортировать их в `strategies/generated/`, выбрать одну из них во вкладке `Стратегии`, подготовить/подтвердить Default workflow и запустить `nfqws2` так, что это уже срабатывает как минимум для YouTube в целевом окружении владельца.

Текущая ветка открывает `v0.4-alpha`. Цель нового цикла — применить ту же цепочку к desktop-версии Discord: подобрать рабочие target domains/probes, научиться получать generated strategy, выбирать её и запускать Default workflow для оживления Discord. На протяжении `v0.4-*` осознанно игнорируется более сложная задача композиции «YouTube + Discord одновременно»: достаточно научиться выбирать и запускать стратегию под один целевой сервис за раз.

`v0.4-alpha_stage_4` выравнивает Discord discovery и runtime: `discord-desktop` targets из registry теперь покрыты `profiles/hostlists/default.hosts`, а тесты ловят будущий дрейф между Blockcheck preset и Default workflow hostlist. YouTube baseline остаётся в том же hostlist; одновременная работа YouTube и Discord по-прежнему не гарантируется как цель цикла.

`v0.4-alpha_stage_7` добавляет failure-driven coverage loop для Discord desktop: preset расширен updater/download target-ом `stable.dl2.discordapp.net`, Blockcheck Lab умеет `scan-all-targets`, candidate logs сохраняются per-target, а generated strategies получают coverage snapshot. Это исправляет главный вывод первой проверки: успех на `discord.com` больше не считается доказательством, что desktop updater прошёл `Checking for updates`.


```bash
python tools/gui_checks/check_project_tree.py
python tools/gui_checks/inventory_core.py --check
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

## v0.3-beta Stage 1: default build workflow

Перед первым `default-start` должен существовать исполняемый `core/zapret2/nfq2/nfqws2`. Если его нет, используйте отдельный owner-confirmed build workflow без `sudo`:

```bash
PYTHONPATH=gui python -m zap2_gui.app --default-build-plan
PYTHONPATH=gui python -m zap2_gui.app --runtime-confirm runtime-default-manual-local-default-build-workflow-plan
PYTHONPATH=gui python -m zap2_gui.app --default-build --confirm runtime-default-manual-local-default-build-workflow-plan
```

После успешной сборки заново подготовьте и подтвердите `--default-start-plan`, затем запускайте `--default-start` через `sudo`. Сборка вынесена отдельно намеренно: `default-start` требует `sudo` для nftables, а build artifacts не должны становиться root-owned.

## Stage 14: default start/stop workflow

Начиная с `v0.3-alpha_stage_14`, дефолтную стратегию можно вести через composite workflow:

```bash
PYTHONPATH=gui python -m zap2_gui.app --default-start-plan
PYTHONPATH=gui python -m zap2_gui.app --runtime-confirm runtime-default-manual-local-default-start-workflow-plan
sudo PYTHONPATH=gui python -m zap2_gui.app --default-start --confirm runtime-default-manual-local-default-start-workflow-plan
```

Отключение:

```bash
PYTHONPATH=gui python -m zap2_gui.app --default-stop-plan
PYTHONPATH=gui python -m zap2_gui.app --runtime-confirm runtime-default-manual-local-default-stop-workflow-plan
sudo PYTHONPATH=gui python -m zap2_gui.app --default-stop --confirm runtime-default-manual-local-default-stop-workflow-plan
```

Этот workflow не является bootstrap: он не скачивает код, не вызывает upstream installer scripts и не включает service mode. Реальные `default-start/default-stop` остаются локальными owner-confirmed действиями, а проверки используют fake runner без root.

Начиная с `v0.3-beta_stage_3`, при запуске через `sudo` session runner передаёт `nfqws2` явный `--uid=<SUDO_UID>:<SUDO_GID>`. Это нужно потому, что upstream `nfqws2` по умолчанию сбрасывает root в synthetic UID/GID `2147483647`, который может не иметь доступа к hostlist внутри пользовательского workspace. Если session падает уже после применения nftables owner-rules, default workflow автоматически выполняет подтверждённый child-revert и удаляет owned table `inet zap2_default`.


## Build dependency preflight

Начиная с `v0.3-beta_stage_2`, перед локальной сборкой можно проверить системные dev-зависимости без установки пакетов и без запуска `make`:

```bash
PYTHONPATH=gui python -m zap2_gui.app --default-build-deps
```

Если отсутствуют заголовки вроде `libnetfilter_queue/libnetfilter_queue.h`, команда покажет missing dependency и owner action hints для популярных дистрибутивов. Само приложение не вызывает `sudo apt install` и не смешивает dependency setup с bootstrap/runtime.

## v0.3-beta Stage 4: Default strategy import и GUI runtime controls

Stage 4 переносит первую базовую стратегию из Windows GUI: `Default v1 (game filter)`. Перенос частичный и контролируемый: оригинальный Windows preset хранится как reference, а Linux runtime получает только seed hostlist и минимальные `nfqws2`-совместимые Lua-аргументы. Полный WinDivert preset не исполняется напрямую.

Также Stage 4 переносит CLI build/start/stop/status workflow во вкладку `Обзор` PyQt shell. GUI не запускает `sudo` и не применяет firewall скрыто: он готовит планы, подтверждает plan id через существующий confirmation gate и показывает owner-команды для терминала.
## v0.3-beta Stage 5: GUI polkit bridge

Privileged включение и отключение default workflow теперь доступны из PyQt GUI через `pkexec`/polkit. GUI не хранит пароль, не просит терминальный `sudo` после нажатия кнопки и не обходит runtime confirmation gate.


## v0.3-dev Stage 16: meta tools, tools layout и safer NFQUEUE scope

Stage 16 переводит ветку в `v0.3-dev`, добавляет `meta_tools/devctl/` как локальный снимок инструмента devctl, разделяет `tools/` на `gui_checks/`, `experimental/` и `lowlevel/`, а также ужесточает default nftables interception. Теперь apply-plan строит правила из активной strategy, не добавляет UDP/443 без `--filter-udp`, ограничивает очередь UID владельца и добавляет loop guard по `--fwmark=0x40000000`, чтобы не ловить root/NetworkManager traffic и не переочередить пакеты, сгенерированные nfqws2.


## v0.3-dev Stage 17: saved owner-rules execution

Stage 17 чинит отказ запуска после Stage 16: GUI мог показать новый start-plan,
подтвердить его, но privileged `sudo -A` path падал на child apply с ошибкой
`Prepared owner-rules plan устарел`. Теперь apply/revert executor исполняет
сохранённый owner-confirmed plan после проверки его собственного hash, не
пересчитывая UID/команды заново под root. Заодно nft loop guard записывается
как `meta mark & 0x40000000 == 0`.

## v0.3-dev Stage 1: GUI Blockcheck lab и сброс нумерации dev-цикла

Начиная с этого патча нумерация внутри `v0.3-dev` считается заново: предыдущие
Stage 16/17 остаются переходными beta/dev hotfix-слоями, а первый нормальный dev
stage получает номер `Stage 1`.

Stage 1 добавляет вкладку `Диагностика: Blockcheck lab`. Это GUI/CLI-обёртка
над vendored upstream `core/zapret2/blockcheck2.sh` для ручного подбора стратегии
под YouTube или другой домен. Дефолтный target — `youtube.com www.youtube.com`,
включены HTTPS TLS1.2/TLS1.3 и HTTP/3 QUIC, DNS precheck по умолчанию пропущен,
чтобы не смешивать подбор стратегии с отдельной диагностикой DNS.

CLI-эквиваленты:

```bash
PYTHONPATH=gui python -m zap2_gui.app --blockcheck-preflight
PYTHONPATH=gui python -m zap2_gui.app --blockcheck-plan --blockcheck-domains "youtube.com www.youtube.com"
PYTHONPATH=gui python -m zap2_gui.app --blockcheck-run --blockcheck-domains "youtube.com www.youtube.com"
PYTHONPATH=gui python -m zap2_gui.app --blockcheck-last-log
```

`--blockcheck-plan` не исполняется и явно показывает, что реальный run идёт
через `sudo -A/SUDO_ASKPASS`, не хранит пароль, не вызывает upstream installer
scripts и не создаёт persistent service. Сам upstream blockcheck временно меняет
firewall redirect для теста и должен запускаться при выключенном Default
workflow, VPN и других DPI-bypass процессах. Для полноценного запуска обычно
нужны локально собранные `core/zapret2/nfq2/nfqws2` и `core/zapret2/mdig/mdig`;
если их нет, `--blockcheck-preflight` покажет owner-action hint.


## v0.3-dev Stage 2: Blockcheck prerequisites build guard

Stage 2 чинит первый реальный запуск Blockcheck lab: upstream `blockcheck2.sh`
требует локально собранные `nfqws2` и `mdig`, а в свежем workspace их может не
быть. Теперь вкладка диагностики имеет отдельные кнопки `План binaries` и
`Собрать binaries`, которые показывают/запускают локальный `make all` без sudo,
без installer scripts и без изменений firewall/services.

`--blockcheck-run` дополнительно останавливается до `sudo -A`, если preflight
видит отсутствующие binaries или другие prerequisites, и пишет понятный last log
в `.zap2/blockcheck/logs/last-blockcheck.txt`.

## v0.3-dev Stage 3: Blockcheck live streaming без заморозки окна

Stage 3 чинит следующую проблему реального запуска: `blockcheck2.sh` может долго
перебирать стратегии, а прежний GUI запускал его синхронно и поэтому вся вкладка
помечалась как «не отвечает». Теперь кнопка `Запустить blockcheck` стартует
процесс через Qt `QProcess`, stdout/stderr подгружаются в поле лога по мере
появления, а окно остаётся отзывчивым.

Произвольный общий таймер для scan не используется по умолчанию. Вместо этого
есть явная кнопка `Остановить`: владелец может прервать долгий поиск, не теряя
уже накопленный вывод. `.zap2/blockcheck/logs/last-blockcheck.txt` обновляется
во время live-run и после завершения/остановки.

## v0.3-dev Stage 4: Lua-safe Blockcheck worker UID/GID

Stage 4 чинит следующий реальный запуск Blockcheck lab. После сборки binaries и
перехода на live streaming upstream `blockcheck2.sh` смог начать scan, но каждая
`nfqws2`-проба падала с ошибкой доступа к `core/zapret2/lua/zapret-lib.lua`.
Причина в upstream default: `blockcheck2.sh` запускает `nfqws2` как root, а затем
передаёт ему `--uid $WS_UID:$WS_GID`; если `WS_UID/WS_GID` не заданы, используются
`1:3003`. Такой synthetic user часто не может пройти по приватному пути
workspace внутри `/home/<owner>/...`, поэтому Lua-файлы существуют, но становятся
недоступными после privilege drop.

GUI/CLI wrapper теперь явно передаёт в blockcheck environment `WS_UID` и `WS_GID`
владельца процесса, который запускает GUI. Если wrapper сам запущен из-под sudo,
приоритет имеют `SUDO_UID/SUDO_GID`; иначе берутся текущие `uid/gid` процесса.
Это сохраняет upstream модель «root только для firewall/NFQUEUE, worker без root»,
но делает чтение Lua-файлов совместимым с пользовательским workspace.

`Blockcheck plan` теперь показывает `blockcheck worker uid/gid` и включает
`WS_UID/WS_GID` в список environment passed to blockcheck2.sh. Preflight также
проверяет наличие Lua support files, чтобы отличать проблему отсутствующих файлов
от проблемы доступа после privilege drop.

## v0.3-dev Stage 5: Blockcheck run statistics after Stop

Stage 5 делает долгие Blockcheck-прогоны более читаемыми после ручной остановки
или штатного завершения. GUI теперь парсит уже накопленный stdout/stderr и
добавляет в финальный блок краткую статистику: сколько `nfqws2`-стратегий было
увидено, сколько дали `AVAILABLE`, сколько завершились `UNAVAILABLE`, сколько
осталось в неизвестном состоянии на момент Stop, как прошёл port precheck и
какая причина недоступности встречалась чаще всего.

Та же статистика сохраняется в `.zap2/blockcheck/logs/last-blockcheck.txt` в
отдельной секции `BLOCKCHECK RUN STATISTICS`, поэтому её можно посмотреть позже
через кнопку `Последний лог` или CLI `--blockcheck-last-log`, даже если исходный
live-output был очень длинным.

## v0.3-dev Stage 6: Blockcheck → generated strategies → selection

Stage 6 замыкает первую полноценную пользовательскую цепочку подбора: после
Blockcheck run кнопка `Создать стратегии` читает последний лог, извлекает
реальные `AVAILABLE` строки `nfqws2`, создаёт отдельные JSON-стратегии в
`strategies/generated/` и добавляет их в `strategies/catalog.json`.

Новая вкладка `Стратегии` теперь показывает каталог как интерактивный список,
отображает детали выбранной стратегии и позволяет явно выбрать одну strategy для
Default profile. Выбор сохраняется в `.zap2/strategies/default.active-strategy.json`
и не запускает сеть сам по себе: следующие Default build/start/stop/status plans
строятся по выбранной strategy id, а запуск всё равно требует обычный
plan/confirmation/sudo-askpass workflow.

CLI-эквиваленты:

```bash
PYTHONPATH=gui python -m zap2_gui.app --blockcheck-export-strategies
PYTHONPATH=gui python -m zap2_gui.app --select-strategy <strategy-id>
PYTHONPATH=gui python -m zap2_gui.app --list-strategies
PYTHONPATH=gui python -m zap2_gui.app --show-strategy <strategy-id>
```

## v0.3-dev Stage 7: sequential Blockcheck candidates и dead-target guard

Stage 7 делает Blockcheck lab более пригодным для реального подбора стратегии. GUI больше не обязан тратить сотни проверок на target, который уже провалил базовый TCP/443 port precheck: если upstream-лог показывает `0 connects / N failed`, текущий candidate автоматически останавливается с verdict `port-precheck-dead-target`, а следующий домен из списка запускается отдельно. Это не wall-clock timeout, а evidence-based остановка по фактам из самого blockcheck output.

Экспорт стратегий теперь берёт источник из `latest-successful-blockcheck.txt`, который обновляется только когда в run были реальные `AVAILABLE` strategy attempts. Поэтому неудачный последний запуск, например с мёртвым `youtube.com:443`, не затирает предыдущий пригодный результат для кнопки «Создать стратегии».

## v0.3-stable: первая подтверждённая end-to-end цепочка

Владелец проекта забэкапировал состояние после `v0.3-dev_stage_7` как `v0.3-stable`. Практически значимый результат этой точки:

```text
Blockcheck lab -> AVAILABLE стратегии -> generated strategy files -> выбор стратегии -> Default workflow start -> работающий YouTube
```

Это не означает универсальную готовность для всех сервисов и сетей. Но это меняет статус проекта: GUI больше не является только plan-only оболочкой. В рамках контролируемой owner-confirmed модели он умеет довести пользователя от диагностики до реально работающего `nfqws2` runtime для конкретного сервиса.

## v0.4-alpha Stage 0: открытие Discord desktop cycle

Этот документационный baseline переводит продуктовую метку в `v0.4-alpha` и сбрасывает нумерацию stage внутри новой вехи. Следующие реализационные патчи должны начинаться с `v0.4-alpha_stage_1`.

Фокус `v0.4-*` — desktop Discord. Ближайшие задачи:

- понять, какие домены/протоколы реально важны для desktop-клиента в окружении владельца;
- прогнать Blockcheck lab по этим candidate targets без возврата к заморозке GUI и бессмысленным scan-циклам;
- экспортировать найденные Discord-стратегии в `strategies/generated/`;
- выбрать одну Discord-стратегию во вкладке `Стратегии`;
- запустить Default workflow и проверить, что desktop Discord оживает.

Нефокус для `v0.4-*`: автоматическое объединение стратегий YouTube и Discord в одну без конфликтов. Пока достаточно сценария «выбрать стратегию под YouTube» или «выбрать стратегию под Discord».

## v0.4-alpha Stage 1: roadmap выбора YouTube или Discord

Stage 1 не меняет runtime и не запускает новые privileged действия. Он фиксирует
план патчей для всей `v0.4-*` вехи: финальная цель цикла — не универсальная
композиция всех сервисов, а понятный выбор целевого сервиса.

Минимальный финальный UX:

```text
выбрать YouTube -> использовать YouTube strategy -> запустить Default workflow
или
выбрать Discord -> использовать Discord strategy -> запустить Default workflow
```

Одновременная работа YouTube и Discord в рамках одной активной стратегии не
гарантируется. Это допустимо только как побочный успех конкретной стратегии, но
не как обязательный критерий готовности `v0.4-*`.

Ближайший реализационный путь после этого stage:

- добавить registry service target presets `youtube-basic`, `discord-desktop`,
  `custom`;
- вывести preset selector в Blockcheck Lab и CLI;
- дополнить Discord hostlist/runtime alignment для `gateway.discord.gg`,
  `cdn.discordapp.com`, `media.discordapp.net`;
- сделать generated strategies service-aware, чтобы не путать YouTube и Discord
  результаты;
- проверить Discord desktop non-voice через существующий owner-confirmed Default
  workflow;
- voice/UDP рассматривать отдельно после подтверждения non-voice слоя.

Полный roadmap зафиксирован в `docs/V04_ALPHA_PATCH_ROADMAP.md`.

## v0.4-alpha Stage 2: registry service target presets

Stage 2 добавил единый кодовый registry `gui/zap2_gui/models/service_targets.py`.
Он хранит `youtube-basic`, `discord-desktop` и `custom`, но не менял GUI selector,
CLI-флаг preset, hostlist или runtime apply. Default Blockcheck сохранил
YouTube baseline `youtube.com www.youtube.com`.

## v0.4-alpha Stage 3: Blockcheck Lab preset selector

Stage 3 подключает registry к пользовательскому Blockcheck path:

- в Blockcheck Lab появился selector `Service target`;
- `YouTube basic` и `Discord desktop non-voice` автозаполняют поле targets из registry;
- preset-owned targets отображаются как read-only, чтобы пользователь не думал,
  что редактирует сам registry;
- `Custom manual targets` возвращает редактируемое поле и запоминает последнюю
  ручную строку при переключении между preset-ами;
- CLI получил `--blockcheck-target-preset`, а `--blockcheck-domains` теперь
  работает как ручной custom override.

Этот stage всё ещё не меняет `runtime_apply` и не гарантирует, что найденная
Discord strategy будет применена ко всем нужным hostlist entries. Следующий шаг —
Discord hostlist/runtime alignment.

## v0.4-alpha Stage 4: Discord hostlist/runtime alignment

Stage 4 закрывает первый практический разрыв между Blockcheck discovery и
Default workflow: домены, которые `discord-desktop` отдаёт в Blockcheck Lab,
теперь присутствуют в `profiles/hostlists/default.hosts`. Особенно важные
entries добавлены явно:

```text
gateway.discord.gg
cdn.discordapp.com
media.discordapp.net
```

Default hostlist при этом сохраняет YouTube baseline. Runtime apply/session не
получают новый скрытый режим «лечить всё сразу»: выбранная strategy всё ещё одна,
а hostlist является общим owner-maintained seed, через который Default workflow
передаёт targets в `nfqws2`. Новые тесты проверяют, что `youtube-basic` и
`discord-desktop` не расходятся с default hostlist.

## v0.4-alpha Stage 5: service-aware export и Strategy UX

Stage 5 делает Blockcheck export осведомлённым о выбранном service target preset.
Теперь `BlockcheckOptions` сохраняет `service_target_preset_id`, план запуска
пишет строку `service target preset: ...`, а окружение blockcheck получает
`ZAP2_SERVICE_TARGET_PRESET`. Это важно для sequential scan: успешный лог может
относиться только к одному candidate вроде `gateway.discord.gg`, но экспорт всё
равно помечает generated strategy как `discord-desktop`, если именно этот preset
запускал проверку.

Generated strategies теперь получают service-aware id/title/metadata:

```text
blockcheck-discord-desktop-gateway.discord.gg-YYYYMMDD-HHMMSS-01
```

В JSON стратегии появляется блок `serviceTarget`, а `sourcePreset` дополнительно
хранит `serviceTargetPresetId`. Вкладка `Стратегии` и CLI-форматтеры показывают
service target label, чтобы владелец не путал YouTube-generated и
Discord-generated результаты. Активной для Default profile всё ещё остаётся
одна выбранная strategy: Stage 5 не вводит автоматическое объединение YouTube и
Discord и не обещает их одновременную работу.


## v0.4-alpha Stage 6: Discord owner verification loop

Stage 6 добавляет проверочную петлю перед личной проверкой Discord desktop non-voice. Она не исполняет сетевые действия сама: владелец видит последовательность Blockcheck/export/select/default-start и затем заполняет локальный отчёт.

```bash
PYTHONPATH=gui python -m zap2_gui.app --discord-verification-plan
PYTHONPATH=gui python -m zap2_gui.app --discord-verification-template
```

Шаблон отчёта создаётся в `.zap2/verification/discord-non-voice-owner-check.md`, не перезаписывает ручные заметки и явно исключает voice/UDP из критерия успеха. GUI-эквивалент плана доступен во вкладке Blockcheck lab через кнопку `Discord checklist`.

## v0.4-alpha Stage 7a — service coverage policy/tournament

Stage 7a добавляет универсальный слой service coverage policy поверх target presets. Теперь registry явно различает:

```text
any-target-available — достаточно одного рабочего target, например youtube-basic
maximize-targets — порядок не важен, но нужно максимальное покрытие
ordered-target-chain — порядок важен, например Discord desktop updater → app/API → gateway → CDN/media
```

Для `discord-desktop` порядок target-ов теперь начинается с updater-фазы `stable.dl2.discordapp.net` / `updates.discord.com`, потому что owner verification упиралась в `Checking for updates`. GUI получил read-only `Policy` и `Tournament` actions, а CLI получил:

```bash
PYTHONPATH=gui python -m zap2_gui.app --blockcheck-service-policy --blockcheck-target-preset discord-desktop
PYTHONPATH=gui python -m zap2_gui.app --blockcheck-tournament --blockcheck-target-preset discord-desktop
```

Этот слой не запускает sudo и не доказывает одну `nfqws2`-команду на всех доменах автоматически; он фиксирует общий контракт для следующего шага и делает текущую диагностику updater-first.



## v0.4-alpha Stage 7b — phase-aware one-strategy tournament

Stage 7b уточняет модель Stage 7a по схеме владельца: стратегии проверяются по одной, а не пачкой `N` стратегий на одном домене. Одна стратегия-кандидат идёт через цепочку фаз и либо становится новым рекордсменом, либо попадает в непрошедшие.

Универсальный контракт теперь такой:

```text
any-target-available — достаточно любого рабочего target, как в простом YouTube baseline
maximize-targets — порядок не важен, но нужно максимизировать покрытие
ordered-target-chain — порядок важен; фазы идут через AND, targets внутри фазы идут через OR
```

Для Discord desktop non-voice цепочка фаз выглядит так:

```text
1. updater/bootstrap: stable.dl2.discordapp.net OR updates.discord.com
2. app-api: discord.com
3. gateway: gateway.discord.gg
4. cdn-media: cdn.discordapp.com OR media.discordapp.net OR discord.media OR discordapp.net
5. invite: discord.gg
```

Это исправляет ошибку Stage 7a: `updates.discord.com` больше не является абсолютным первым blocker-ом, если та же updater-фаза может быть пройдена через `stable.dl2.discordapp.net`.

Добавлен план one-strategy validation через upstream custom lists. Он записывает ровно одну `nfqws2`-стратегию в `.zap2/blockcheck/tournament/custom-lists/<strategy>/list_https_tls12.txt` и `list_https_tls13.txt`, чтобы следующий шаг мог проверять кандидата по фазам без предварительного накопления произвольной пачки стратегий на одном target-е.

CLI read-only пример:

```bash
PYTHONPATH=gui python -m zap2_gui.app --blockcheck-tournament --blockcheck-target-preset discord-desktop
PYTHONPATH=gui python -m zap2_gui.app --blockcheck-validate-strategy-plan <strategy-id> --blockcheck-domains discord.com
```

Граница Stage 7b: патч фиксирует фазовую модель, record-holder семантику и one-strategy custom-list bridge. Полный автоматический GUI-run, который сам берёт кандидата, гонит его по всем фазам и останавливается на полном покрытии, остаётся следующим реализационным слоем поверх этого контракта.

## v0.4-alpha Stage 7c — phase-gated tournament runner correction

Stage 7c corrects the Stage 7b runner mismatch observed during owner testing: the GUI must not continue to later Discord phases after an earlier required phase has no AVAILABLE alternative. The previous Stage 7b report described one-strategy tournament semantics, but the live `Scan all preset targets` runner still behaved like raw target coverage and could continue from blocked updater/app/gateway phases to a later CDN target.

The GUI Blockcheck runner is now phase-gated for presets with `ordered-target-chain` policy:

```text
phase 1 alternatives are tested first
if any alternative becomes AVAILABLE -> stop that candidate and advance to phase 2
if every alternative in the current required phase fails/dead-targets -> stop before later phases
later phases are never scanned out of order just because they appear later in the domain list
```

For Discord desktop non-voice this means:

```text
updater/bootstrap: stable.dl2.discordapp.net OR updates.discord.com
then app-api: discord.com
then gateway: gateway.discord.gg
then cdn-media alternatives
then invite
```

This patch intentionally preserves the Stage 7b one-strategy custom-list bridge. The full automatic record-holder validator is still a separate layer, but the GUI no longer produces misleading "random later domain" evidence when the ordered phase chain has already blocked.


## v0.4-alpha Stage 7d — Discord port-precheck и Blockcheck Lab UX

Stage 7d фиксирует два наблюдения owner-run после Stage 7c.

Первое: `stable.dl2.discordapp.net` уже давал десятки `AVAILABLE` стратегий, но следующий запуск мог пометить его `dead-target` на основании одного неудачного `nc` в port precheck. Для Discord ordered phases это слишком агрессивно: CDN/updater адреса могут быть плавающими, а `nc`-проверка не должна блокировать сам подбор стратегии. Поэтому Blockcheck Lab получил режим `dead-target guard`: для простых проверок он остаётся `auto-stop`, а для `discord-desktop` по умолчанию выставляется `observe-only`. В `observe-only` портовый precheck остаётся в логе и статистике, но GUI не убивает candidate до strategy scan.

Второе: экран Blockcheck Lab стал слишком плотным после добавления service policy/tournament controls. Stage 7d расширяет дефолтное окно, делит действия на две строки, укорачивает подписи кнопок и добавляет явный переключатель `Auto-skip dead target`, чтобы владелец видел, когда включён риск раннего пропуска candidate.

Граница Stage 7d: патч не портирует Flowseal/Windows presets в исполняемый Linux runtime автоматически. Он фиксирует источник ложного `dead-target`, улучшает управляемость GUI и документирует, какие идеи Flowseal/Windows стоит переносить осторожно.

## v0.4-alpha Stage 7f — bounded phase alternatives and core notes

Stage 7f fixes the owner-observed case where the phase-gated runner stayed on the first updater alternative (`stable.dl2.discordapp.net`) until manual Stop. The runner still follows the owner model — phases are `AND`, alternatives inside a phase are `OR`, and later phases are not checked until the current required phase is satisfied — but each phase alternative now has an owner-visible `Alt check cap`.

For `discord-desktop` the default cap is 160 strategy checks per alternative. If an `AVAILABLE` strategy appears first, the GUI stops that upstream candidate and advances to the next phase. If the cap is reached with no `AVAILABLE`, the GUI stops only that candidate and tries the next alternative in the same phase. Setting the cap to `off` restores the previous unbounded behavior for deep single-target scans.

Stage 7f also records core reference notes from `core/zapret2`: upstream custom blockcheck lists can be supplied via `LIST_HTTP`, `LIST_HTTPS_TLS12`, `LIST_HTTPS_TLS13` and `LIST_QUIC`, and `nfqws2` profile ordering is first-match-wins. These notes are captured in `docs/ZAPRET2_CORE_BLOCKCHECK_NOTES.md` for the future real one-strategy validator and possible multi-profile Discord runtime work.

The Blockcheck Lab layout is widened again and key controls now have maximum widths plus a reserved two-line preset description area, so the diagnostics screen is less edge-stretched and less vertically overlapped.

### v0.4-alpha Stage 7g — Discord endpoint discovery

The diagnostics tab now has an `Endpoints` action for the Discord updater dead end. It prints a read-only plan and latest report. The CLI watch is:

```bash
PYTHONPATH=gui python -m zap2_gui.app --discord-endpoint-watch --discord-endpoint-seconds 90
```

Run the watch, start Discord during the window, leave it on `Checking for updates`, then inspect:

```bash
PYTHONPATH=gui python -m zap2_gui.app --discord-endpoint-report
```

This does not require sudo, does not mutate firewall/services and does not capture payloads. It samples visible process socket metadata only.

### v0.4-alpha Stage 7h — Discord updater endpoint deep discovery

Stage 7h adds TCP state/timer and DNS matching to the Discord endpoint watcher. If the Discord splash shows `Checking for updates` while the watcher reports `SYN-SENT` for a `updates.discord.com` edge IP, the current blocker is before a completed TLS/HTTP exchange on that socket. Use `--discord-netlog-plan` only as an owner-run, privacy-aware follow-up; raw Chromium netlogs should be reviewed and redacted before sharing.

### v0.4-alpha Stage 7i — Discord DNS edge diagnosis

Stage 7i переносит идею Windows GUI DNS-проверок в read-only Linux diagnostic. Команды `--discord-dns-edge-plan` и `--discord-dns-edge-check` сравнивают system/Cloudflare/Google/Quad9/AdGuard/OpenDNS resolvers и проверяют TCP/443 для возвращённых Discord edge IP. Это не меняет DNS и не требует sudo. Если найден `connect-ok` edge, DNS/hosts steering можно рассматривать как owner-confirmed эксперимент. Если все edge IP timeout, то текущий Discord updater blocker шире, чем DNS-подмена, и обычные TLS Blockcheck-стратегии всё ещё не упражняются на SYN-SENT socket.
