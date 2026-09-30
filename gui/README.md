# GUI-пакет

Текущий кандидат: **0.9.0rc5 / P05 RC5**, последний принятый релиз — v0.8. P05 добавляет глобальный поиск/справку по ActionContracts и ontology, structured error envelopes и отдельные health projections. В GUI: Ctrl+K; приёмка: `bash meta_tools/hyperpatch_acceptance.sh --p05`. Документ: `docs/P05_DISCOVERABILITY.md` (из `docs/`: `P05_DISCOVERABILITY.md`).

Runtime executor и plan/confirm уже реализованы в P02–P04 (`gui/zap2_gui/adapters/`); `runtime/` содержит схемы и evidence. P05 не меняет authority исполнения. Полный S-INSTALL и физическая реорганизация документации остаются для P06.

## Исторический контекст и указатель предыдущих этапов

`gui/` содержит наш application-side Python-код и развивается в desktop GUI на PyQt. Он не должен поглощать upstream-исходники ядра и не должен выполнять privileged host mutations во время import.

Начиная с `v0.3-alpha_stage_5`, пакет содержит первый скелет GUI shell:

- `app.py` — CLI-visible entry point и optional GUI launcher;
- `qt_compat.py` — безопасная проверка доступности PyQt6;
- `qt_app.py` — локальный `QApplication` bootstrap;
- `models/navigation.py` — pure Python модель разделов;
- `windows/main_window.py` — фабрика главного окна PyQt;
- `widgets/placeholders.py` — начальные placeholder-страницы;
- `adapters/gui_state.py` — read-only сборка состояния для оболочки;
- `adapters/local_build.py` — plan-only adapter локальной сборки ядра.

Стартовая навигация фиксирует разделы: `Обзор`, `Ядро`, `Стратегии`, `Диагностика`, `Настройки`, `Логи`. Раздел `Ядро` уже может показывать сведения из inventory/build map, остальные разделы остаются намеренными placeholder-страницами для следующих патчей.

PyQt6 добавлен как optional dependency `gui`, а не как обязательное условие devctl-проверок. Поэтому `python -m zap2_gui.app` должен работать в headless-среде без установленного Qt, а `python -m zap2_gui.app --gui` предназначен для локальной машины разработчика с установленным PyQt6 и display server.

Не переключать shell на PySide, GTK, Tkinter, Electron или CLI-only interface без явного решения владельца. Non-UI логика — inventory, build-plan generation, diagnostics и privilege planning — должна оставаться pure Python, чтобы её можно было тестировать отдельно от Qt.

## Local build adapter

`local_build.py` создаёт план локальной сборки на основе `BUILD_MAP.json`. Он возвращает `cwd`, `argv`, ожидаемые артефакты и флаги безопасности, но не вызывает `make` сам. Это даёт GUI стабильный контракт для будущего экрана сборки и позволяет тестировать workflow без Qt, без sudo и без системных изменений.

## Stage 7: workspace-профили и стратегии

GUI-слой теперь умеет читать профили и стратегии через `zap2_gui.adapters.workspace_profiles`. Это read-only adapter: он валидирует JSON-файлы в `profiles/` и `strategies/`, связывает профиль с `strategyId` и `buildTarget`, но не запускает стратегию и не применяет настройки к системе.

CLI-команды для проверки слоя:

```bash
PYTHONPATH=gui python -m zap2_gui.app --list-profiles
PYTHONPATH=gui python -m zap2_gui.app --show-profile default
PYTHONPATH=gui python -m zap2_gui.app --list-strategies
PYTHONPATH=gui python -m zap2_gui.app --show-strategy manual-local
```

В PyQt shell вкладка `Стратегии` получает статус `profiles-backed`. На этой стадии она показывает данные и safety boundary, но не редактирует профиль и не выполняет runtime lifecycle.


## Runtime lifecycle contracts

Начиная со Stage 8 GUI-слой умеет читать и валидировать runtime lifecycle contracts через `gui/zap2_gui/adapters/runtime_contracts.py`. Это не кнопка запуска и не executor. Adapter нужен, чтобы будущие PyQt-экраны показывали владельцу run/apply/session/service plans, confirmation status и rollback notes как структурированные данные.

CLI-команды `--runtime-contracts` и `--validate-runtime-contracts` доступны без установленного PyQt6 и ничего не исполняют.


## Stage 9: runtime plan generator

GUI-слой теперь содержит `adapters/runtime_plan_generator.py`. Он нужен будущей вкладке “Стратегии/Runtime”, чтобы показывать владельцу конкретные планы `start`, `stop` и `status` для default profile. Adapter читает project data и строит текст/модель плана, но не исполняет команды.


## Runtime state CLI Stage 10

GUI package теперь содержит `adapters/runtime_state.py`. Этот adapter обслуживает будущую вкладку `Логи` и будущий controlled runtime workflow: создаёт `.zap2/runtime`, сохраняет prepared plans, rollback notes, confirmations и JSONL events. Код остаётся pure Python и не требует PyQt для тестов.

CLI-команды `--runtime-prepare`, `--runtime-confirm` и `--runtime-log` ничего не исполняют и не требуют `sudo`; они только создают локальный workspace trace.


## Runtime session runner

GUI/application layer теперь содержит guarded adapter `runtime_session.py`. Его CLI-команды:

```bash
PYTHONPATH=gui python -m zap2_gui.app --runtime-session-start --profile default
PYTHONPATH=gui python -m zap2_gui.app --runtime-session-status --profile default
PYTHONPATH=gui python -m zap2_gui.app --runtime-session-stop --profile default
```

Adapter требует prepared/confirmed start-plan, пишет session state в `.zap2/runtime/sessions/`, ведёт runtime log и не управляет firewall, routing или systemd. Будущий PyQt экран `Стратегии` сможет использовать этот слой для кнопок session start/status/stop, но privileged apply/revert должен остаться отдельным workflow.


## Stage 12: apply/revert как GUI-данные

GUI-слой получил adapter `runtime_apply.py`. Будущие PyQt-экраны должны показывать owner-rules plan, confirmation status, rollback notes и результат apply/revert как структурированные данные. Кнопки применения не должны обходить `planHash`/confirmation gate.

## Stage 13: service plans в GUI-слое

GUI orchestration теперь знает о service mode через `runtime_service.py`. Этот слой пока доступен через CLI и будущий GUI сможет показать его как отдельную карточку: `install/start/stop/remove`, plan hash, unit path, rollback notes и статус “не является дефолтным workflow”.

## Stage 14: default workflow в CLI/GUI shell

GUI-слой получил adapter `runtime_default.py`. На CLI он уже доступен через `--default-start-plan`, `--default-start`, `--default-stop-plan`, `--default-stop`. В будущем GUI должен показывать эти же данные как экран подтверждения, а не как скрытую кнопку.


## v0.3-beta Stage 1: default build workflow в GUI-слое

GUI-слой получил adapter `runtime_default_build.py`. На CLI он доступен через `--default-build-plan` и `--default-build --confirm <plan-id>`. Будущий PyQt экран должен показывать это как отдельный preflight перед `default-start`: сначала собрать `nfqws2` без `sudo`, затем заново подготовить start-plan и только потом запускать owner-confirmed runtime workflow.

Важно не встраивать сборку внутрь `default-start`, потому что `default-start` запускается через `sudo` ради nftables apply. Сборка под root может оставить root-owned artifacts в рабочем дереве и нарушить локальный developer workflow.
## Графический запрос прав

Вкладка `Обзор` содержит кнопки включения и отключения default workflow через `sudo -A`/SUDO_ASKPASS. Перед нажатием privileged-кнопки пользователь всё ещё должен создать plan и сохранить confirmation.


## v0.4-alpha Stage 8f: launcher и sidebar shell

Для обычного запуска больше не нужно вручную писать `PYTHONPATH=gui python -m
zap2_gui.app --gui`: из корня проекта используется `./run.sh`. Без аргументов
он открывает GUI, а переданные аргументы направляет в существующий CLI.

Главное окно использует левую навигацию и `QStackedWidget`, сохраняет геометрию
и последний раздел через `QSettings`. Общая пастельная тема находится в
`zap2_gui/theme.py` и не добавляет `qfluentwidgets` или другую UI-зависимость.


## P04c: ActionContract dispatcher

CLI и GUI начинают сходиться на одной executable action authority. `models/action_catalog.py` содержит pure ActionContracts, `adapters/action_dispatcher.py` связывает их с handlers, а `adapters/legacy_cli.py` переводит совместимые legacy selectors и отвергает противоречивые selector combinations до исполнения. Canonical CLI form для мигрированного slice: `--action <contract-id>`. Overview start/status/stop tooltips читаются из того же catalog. Полная миграция legacy actions остаётся P04d.


## P04d: ActionContract closure

Все 117 historical top-level selectors переводятся в 119 canonical ActionContracts до исполнения. `main()` больше не выбирает action по first-match branch order; compatibility bodies вызываются только выбранным dispatcher contract. Canonical selector values передаются через повторяемый `--operand`.
