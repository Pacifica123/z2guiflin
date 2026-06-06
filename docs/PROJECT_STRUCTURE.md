# Структура проекта

```text
core/
  README.md
  zapret2/
    UPSTREAM_IMPORT.json
    UPSTREAM_IMPORT.md
    CORE_INVENTORY.json
    BUILD_MAP.json
    ... vendored upstream source ...

gui/
  README.md
  zap2_gui/
    __init__.py
    app.py
    core_inventory.py
    project_paths.py
    qt_compat.py
    qt_app.py
    adapters/
      gui_state.py
      local_build.py
      workspace_profiles.py
      runtime_contracts.py
      runtime_plan_generator.py
    models/
      navigation.py
      strategy.py
      workspace_profile.py
      lifecycle.py
      runtime_plan.py
      runtime_events.py
    windows/
      main_window.py
    widgets/
      placeholders.py

profiles/
  README.md
  default.json
  hostlists/
    default.hosts
  examples/
    lab-readonly.json

strategies/
  README.md
  catalog.json
  manual-local.json
  read-only-diagnostics.json

runtime/
  README.md
  schemas/
    runtime-plan.schema.json
    runtime-event.schema.json
    confirmation.schema.json
  examples/
    manual-local-start.contract.json
    manual-local-start.event.json
    manual-local-start.confirmation.json

docs/
  DEVELOPMENT_STRATEGY.md
  VERSIONING.md
  PROJECT_STRUCTURE.md
  SAFETY_AND_PRIVILEGE_BOUNDARY.md
  GUI_FRAMEWORK.md
  GUI_SHELL.md
  DOCUMENTATION_LANGUAGE.md
  CORE_INVENTORY.md
  CORE_BUILD_MAP.md
  LOCAL_BUILD_ADAPTER.md
  WORKSPACE_PROFILES.md
  STRATEGIES.md
  RUNTIME_LIFECYCLE.md
  RUNTIME_PLANS.md
  DEFAULT_RUNTIME_PLAN_GENERATOR.md
  reference/
    windows_gui_feature_digest.md
    legacy_project_digest.md

tools/
  check_project_tree.py
  inventory_core.py
  check_local_build_adapter.py
  check_workspace_profiles.py
  check_runtime_lifecycle.py
  check_runtime_plan_generator.py

tests/
  test_bootstrap_structure.py
  test_gui_framework_decision.py
  test_gui_shell_skeleton.py
  test_documentation_language.py
  test_core_inventory_and_build_map.py
  test_local_build_adapter.py
  test_workspace_profiles_and_strategies.py
  test_runtime_lifecycle_contracts.py
  test_runtime_plan_generator.py
```

## Правило разделения

`core/` — это upstream-исходники ядра. `gui/` — наш продуктовый код. `docs/` описывает решения, reference behavior и правила разработки. Нельзя размывать эти области: не разбрасывать GUI-код по core tree и не превращать документацию в исполняемые install instructions.

## Правило импорта ядра

Импортированные исходники намеренно vendored. Будущие обновления должны быть явными source refresh patches, а не runtime auto-updates. GUI позже может показывать диагностику “новый upstream существует”, но применение такого обновления остаётся решением разработчика.

## Правило GUI-фреймворка и shell

Активный GUI-фреймворк — **PyQt**. Начиная со Stage 5, в дереве есть начальная PyQt shell: navigation model, optional `QApplication` bootstrap, фабрика главного окна и placeholder-страницы. При этом модульный импорт проекта остаётся headless-safe: автоматические проверки не должны требовать установленный PyQt6 или display server.

Стартовые разделы оболочки:

```text
Обзор
Ядро
Стратегии
Диагностика
Настройки
Логи
```

Qt-specific classes должны оставаться рядом с UI layer. Core inventory, build-plan generation и safety/privilege planning должны оставаться pure Python, чтобы их можно было тестировать без display server.

## Правило языка документации

Активная проектная документация ведётся на русском языке. Исключение — vendored upstream-документация внутри `core/zapret2/docs/`, потому что она относится к импортированному ядру и должна сохраняться как source input.

## Метаданные ядра

Stage 4 добавляет два snapshot-файла рядом с vendored-ядром:

- `core/zapret2/CORE_INVENTORY.json` — машинная инвентаризация файлов, расширений, Makefile, Lua-сценариев, service templates и зон, которые потенциально связаны с привилегиями;
- `core/zapret2/BUILD_MAP.json` — машинная карта корневого Makefile, дочерних Makefile и build units `nfqws2`, `ip2net`, `mdig`.

Эти файлы являются нашим слоем описания, а не upstream-исходниками. Они должны обновляться только явным патчем или ручной командой разработчика `python tools/inventory_core.py --write` после осознанного изменения `core/zapret2/`. Автоматические проверки используют `--check` и не запускают сборку.

## Local build adapter

Stage 6 добавляет `gui/zap2_gui/adapters/local_build.py`. Это наш первый adapter между build map и будущим GUI workflow сборки. Он создаёт структурированный план локальной команды `make`, но не выполняет её в автоматических проверках.

Слой считается частью `gui/`, потому что он обслуживает application workflow, а не меняет upstream-ядро. Его проверки находятся в `tools/check_local_build_adapter.py` и `tests/test_local_build_adapter.py`.


## Workspace-профили и стратегии

Stage 7 добавляет два новых top-level слоя данных:

- `profiles/` — workspace-профили владельца, локальные hostlists и примеры профилей;
- `strategies/` — каталог plan-only стратегий, которые будущий GUI сможет показывать и связывать с профилями.

Эти директории намеренно находятся рядом с `core/` и `gui/`, а не внутри vendored-ядра. Они относятся к нашему приложению и описывают пользовательский workflow, но не являются upstream-исходниками и не должны автоматически применять системные изменения.

`gui/zap2_gui/adapters/workspace_profiles.py` читает эти JSON-файлы, валидирует связи `profile -> strategy -> build target` и отдаёт данные CLI/GUI. Вкладка `Стратегии` теперь считается `profiles-backed`, но остаётся read-only: редактирование и применение появятся только отдельными патчами.


## Runtime lifecycle contracts

Stage 8 добавляет top-level директорию `runtime/`. Это наш контрактный слой будущего запуска, применения системных правил, session runner, service mode, runtime events, confirmation gate и rollback notes. Он находится рядом с `profiles/` и `strategies/`, потому что описывает application workflow, а не upstream-ядро.

`runtime/` на Stage 8 не является executor. Файлы в нём можно читать и валидировать, но нельзя автоматически исполнять. Реальный запуск процесса, privileged apply/revert и service management должны появляться отдельными патчами после того, как будут готовы state dir, логи и подтверждения владельца.


## Runtime plan generator

Stage 9 добавляет `gui/zap2_gui/adapters/runtime_plan_generator.py`. Этот adapter не является executor: он строит read-only планы `start`, `stop` и `status` из default profile, manual-local strategy и local build map. CLI-команда `--runtime-plan` выводит эти планы для будущего GUI и будущего confirmation gate, но не запускает процесс и не меняет систему.


## Runtime state store

Stage 10 добавляет локальный workspace state store `.zap2/runtime/`. Он не коммитится как исходный код и не считается bootstrap-слоем. Директория создаётся CLI-командой `--runtime-prepare` и содержит prepared plans, confirmations, future session state, JSONL logs и rollback notes.

```text
.zap2/runtime/plans/
.zap2/runtime/confirmations/
.zap2/runtime/sessions/
.zap2/runtime/logs/
.zap2/runtime/rollback/
```

В исходном дереве Stage 10 добавляет `gui/zap2_gui/adapters/runtime_state.py`, `docs/RUNTIME_STATE_AND_CONFIRMATION.md`, `tools/check_runtime_state.py` и тесты. Системные директории, `/opt`, service units и firewall state этим этапом не создаются.


## Runtime session runner

Stage 11 добавляет `gui/zap2_gui/adapters/runtime_session.py
  gui/zap2_gui/adapters/runtime_apply.py`. Этот файл находится в GUI/application layer, потому что он управляет workflow нашего приложения вокруг vendored-ядра, а не меняет upstream-исходники.

Session state остаётся в `.zap2/runtime/sessions/`, а логи — в `.zap2/runtime/logs/`. Эти файлы не коммитятся, потому что отражают локальное состояние машины владельца. Проверки Stage 11 используют временный fake `nfqws2` в копии workspace, чтобы проверить lifecycle без сборки C-ядра, firewall rules, service manager и повышенных привилегий.


## Stage 12 добавление

`runtime_apply.py` — adapter owner-confirmed apply/revert. Он строит nftables plans, сохраняет их через `.zap2/runtime`, проверяет confirmation и умеет исполнять только подтверждённый plan. Автотесты используют fake runner, поэтому структура проекта остаётся проверяемой без root.

## Дополнение Stage 13: service plans

Начиная со Stage 13 в GUI-слое есть adapter `gui/zap2_gui/adapters/runtime_service.py`. Он не относится к bootstrap и не заменяет session runner. Его задача — описывать service mode как отдельный systemd-oriented план, сохраняемый в `.zap2/runtime`.

Документация решения находится в `docs/RUNTIME_SERVICE_PLANS.md`, а проверка — в `tools/check_runtime_service.py`.

## Дополнение Stage 14

```text
gui/zap2_gui/adapters/runtime_default.py   composite default start/stop workflow
docs/DEFAULT_WORKFLOW.md                   документация запуска/отключения default strategy
tools/check_runtime_default.py             fake-проверка default workflow без root/nft/systemctl
tests/test_default_workflow.py             unit-тесты composite workflow
```
