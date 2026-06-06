# Выравнивание с источниками — v0.3-alpha_stage_4

Входные материалы, использованные для bootstrap:

- `zapret2-core-from_bolvan.zip` — снимок upstream-исходников ядра, переданный владельцем;
- `zapret2-gui_windows.zip` — Windows GUI reference, переданный владельцем;
- архив предыдущего Linux-проекта — используется только как draft notes;
- архив devctl — используется для совместимости с форматом патчей.

Реализованное выравнивание:

- upstream-исходники ядра импортированы в `core/zapret2/` как vendored source;
- upstream MIT license text сохранён в `core/zapret2/docs/LICENSE.txt`;
- скомпилированные binary artifacts из upstream-архива не импортированы в bootstrap;
- идеи Windows GUI суммированы в `docs/reference/windows_gui_feature_digest.md`, а не скопированы как Linux-код;
- старый Linux-проект суммирован в `docs/reference/legacy_project_digest.md` и удалён как active code.

Не-цели:

- сборка ядра не выполняется;
- service/unit integration не добавляется;
- привилегированные команды не выполняются;
- network updater не вводится;
- end-user installer не реализуется.

## Добавление Stage 2

Stage 2 не менял импортированные upstream-исходники. Он зафиксировал решение по GUI-фреймворку для нашего слоя: Linux GUI использует PyQt, с линейкой PyQt 6 как целевой по умолчанию.

## Добавление Stage 3

Stage 3 не меняет импортированные upstream-исходники. Он переводит активную проектную документацию на русский язык и закрепляет правило: будущие изменения нашей документации должны оставаться русскоязычными. Vendored upstream-документация внутри `core/zapret2/docs/` сохраняется как часть исходного импорта и не переводится этим правилом.


## Добавление Stage 4

Stage 4 не меняет импортированные upstream-исходники. Он добавляет наш read-only слой инвентаризации поверх `core/zapret2/`:

- `core/zapret2/CORE_INVENTORY.json` описывает фактический состав vendored-ядра;
- `core/zapret2/BUILD_MAP.json` описывает Makefile, targets и будущие build units;
- `docs/CORE_INVENTORY.md` и `docs/CORE_BUILD_MAP.md` дают русскоязычное объяснение этих snapshot-файлов;
- `tools/inventory_core.py` умеет сверять snapshot с текущим деревом без запуска upstream-кода.

Сборка ядра, установка зависимостей, service integration и привилегированные действия остаются не-целями этого этапа.

## Добавление Stage 5

Stage 5 не меняет импортированные upstream-исходники. Он добавляет наш GUI-layer skeleton поверх уже описанных inventory/build map:

- `gui/zap2_gui/models/navigation.py` фиксирует будущие разделы оболочки;
- `gui/zap2_gui/qt_compat.py` изолирует PyQt6 как optional dependency;
- `gui/zap2_gui/qt_app.py` и `gui/zap2_gui/windows/main_window.py` вводят локальный PyQt bootstrap и главное окно;
- `gui/zap2_gui/widgets/placeholders.py` добавляет стартовые placeholder-страницы;
- `docs/GUI_SHELL.md` документирует правила развития оболочки.

Сборка ядра, установка зависимостей, service integration, firewall mutation и привилегированные действия остаются не-целями этого этапа. Автоматические проверки проверяют импортируемость и структуру GUI shell, но не запускают окно.

## Добавление Stage 6

Stage 6 не меняет импортированные upstream-исходники. Он добавляет наш application-side adapter поверх `BUILD_MAP.json`:

- `gui/zap2_gui/adapters/local_build.py` формирует планы локальной сборки для `all`, `nfqws2`, `ip2net`, `mdig` и `clean`;
- `docs/LOCAL_BUILD_ADAPTER.md` описывает назначение adapter-слоя и его границы;
- `tools/check_local_build_adapter.py` и `tests/test_local_build_adapter.py` проверяют, что план не требует `sudo`, не меняет services/firewall и не запускается автоматически;
- `python -m zap2_gui.app --build-plan` показывает план в headless-режиме без выполнения `make`.

Сборка ядра, установка зависимостей и privileged runtime integration по-прежнему не выполняются автоматическими проверками.

## Stage 7: alignment профилей и стратегий

Workspace-профили и стратегии относятся к нашему приложению, а не к upstream-ядру. Они намеренно вынесены в `profiles/` и `strategies/`, чтобы не смешивать пользовательский workflow с vendored-исходниками `core/zapret2/`.

Из Windows GUI мы берём продуктовую философию “toolbox/apothecary”: владелец видит набор инструментов, рецептов и профилей. При этом мы не копируем Windows-specific service assumptions и не переносим их в Linux слой как скрытую автоматику. На Stage 7 всё остаётся read-only data model.


## Stage 8 и runtime contracts

Runtime lifecycle contracts — это наш application layer поверх vendored-ядра. Они не меняют upstream-исходники и не запускают upstream installer scripts. Их задача — заранее описать будущий запуск/остановку, apply/revert, session runner, service mode, events, confirmations и rollback notes в форме данных.

Такое разделение сохраняет alignment с `core/zapret2/`: ядро остаётся source input, а runtime orchestration развивается в `runtime/` и `gui/zap2_gui/` как отдельный контролируемый слой.


## Stage 9 и default runtime plan generator

Stage 9 также не меняет upstream-исходники. Он добавляет application-side генератор, который читает `profiles/default.json`, `strategies/manual-local.json` и `core/zapret2/BUILD_MAP.json`, чтобы показать будущий `start`, `stop` или `status` план для локального binary `core/zapret2/nfq2/nfqws2`.

Это сохраняет разделение: `core/zapret2/` остаётся vendored source input, а runtime orchestration живёт в нашем Python/GUI слое и пока остаётся plan-only.


## Alignment Stage 10

Runtime state и confirmation gate относятся к нашему application layer, а не к vendored upstream-ядру. Они не меняют `core/zapret2/`, не добавляют installer wrapper вокруг upstream scripts и не смешивают runtime lifecycle с bootstrap.

Stage 10 усиливает исходную цель проекта: все потенциально чувствительные действия сначала должны существовать как данные, затем как saved plan с hash, затем как confirmation, затем как log/rollback trace, и только после этого как owner-confirmed execution в отдельном патче.


## Stage 11 и upstream alignment

Runtime session runner запускает vendored binary `core/zapret2/nfq2/nfqws2`, но не меняет upstream source tree и не использует upstream installer scripts. Args file, PID, logs и session marker создаются в `.zap2/runtime`, то есть в нашем application state layer.

Это сохраняет разделение: upstream-ядро остаётся source input, а наш GUI отвечает за plan/confirmation/session lifecycle вокруг него.


## Stage 12: соответствие upstream interception model

Upstream zapret2 описывает Linux interception через netfilter/nftables/iptables и отделяет `nfqws2` от startup scripts. Stage 12 следует этой модели: мы не запускаем upstream installer scripts и не копируем init/systemd-обвязку, а создаём минимальный собственный nftables backend как application-layer plan.

Default Stage 12 backend intentionally narrow: локальный `output` hook, отдельная table `inet zap2_default`, NFQUEUE `200`. Это не претензия на полное покрытие router-сценариев upstream. Расширение до WAN/LAN профилей должно идти через новые стратегии и profiles, а не через скрытый installer.

## Stage 13: соответствие service mode vendored core

Service plan использует тот же локальный `nfqws2`, который описан в build map и runtime plan generator. Он не скачивает ядро, не вызывает upstream installer scripts и не применяет чужие service templates напрямую. Systemd unit генерируется нашим adapter-слоем как прозрачный plan, а не как bootstrap-установка.

## Stage 14 и отношение к upstream

Default workflow Stage 14 использует vendored upstream binary path `core/zapret2/nfq2/nfqws2`, но не вызывает upstream installer scripts и не копирует upstream service lifecycle. Наш слой отвечает за planHash confirmation, runtime state, logs, rollback notes и owned nftables table `inet zap2_default`.


## v0.3-beta Stage 1 и локальная сборка upstream binary

Default build workflow не меняет upstream-исходники и не добавляет installer wrapper. Он использует `BUILD_MAP.json` и Makefile самого vendored core, чтобы собрать `nfqws2` локально в `core/zapret2/nfq2/`. Это соответствует новой архитектуре проекта: upstream остаётся source core, а наш слой добавляет прозрачные plans, confirmations, logs и state вокруг него.

Сборка не должна выполняться в devctl-проверках и не должна запускаться через `sudo`. Если требуются системные build dependencies, их устанавливает владелец машины вне проекта; GUI лишь показывает план, stderr и статус expected artifacts.
