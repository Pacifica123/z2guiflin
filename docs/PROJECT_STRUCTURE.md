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
    models/
      navigation.py
    windows/
      main_window.py
    widgets/
      placeholders.py

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
  reference/
    windows_gui_feature_digest.md
    legacy_project_digest.md

tools/
  check_project_tree.py
  inventory_core.py
  check_local_build_adapter.py

tests/
  test_bootstrap_structure.py
  test_gui_framework_decision.py
  test_gui_shell_skeleton.py
  test_documentation_language.py
  test_core_inventory_and_build_map.py
  test_local_build_adapter.py
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
