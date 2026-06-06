# GUI-пакет

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
