# Структура проекта

```text
core/
  README.md
  zapret2/
    UPSTREAM_IMPORT.json
    UPSTREAM_IMPORT.md
    ... vendored upstream source ...

gui/
  README.md
  zap2_gui/
    __init__.py
    app.py
    core_inventory.py
    project_paths.py

docs/
  DEVELOPMENT_STRATEGY.md
  VERSIONING.md
  PROJECT_STRUCTURE.md
  SAFETY_AND_PRIVILEGE_BOUNDARY.md
  GUI_FRAMEWORK.md
  DOCUMENTATION_LANGUAGE.md
  reference/
    windows_gui_feature_digest.md
    legacy_project_digest.md

tools/
  check_project_tree.py

tests/
  test_bootstrap_structure.py
  test_gui_framework_decision.py
  test_documentation_language.py
```

## Правило разделения

`core/` — это upstream-исходники ядра. `gui/` — наш продуктовый код. `docs/` описывает решения, reference behavior и правила разработки. Нельзя размывать эти области: не разбрасывать GUI-код по core tree и не превращать документацию в исполняемые install instructions.

## Правило импорта ядра

Импортированные исходники намеренно vendored. Будущие обновления должны быть явными source refresh patches, а не runtime auto-updates. GUI позже может показывать диагностику “новый upstream существует”, но применение такого обновления остаётся решением разработчика.

## Правило GUI-фреймворка

Активный GUI-фреймворк — **PyQt**. Текущее дерево пока может содержать только минимальный Python-пакет, но будущая GUI shell должна целиться в PyQt, а не в PySide, GTK, Tkinter, Electron, browser-first interface или CLI-only application.

Рекомендуемое будущее разделение:

```text
gui/zap2_gui/
  app.py              application entry point
  qt_app.py           PyQt QApplication bootstrap после добавления зависимости
  windows/            top-level windows и navigation shell
  widgets/            переиспользуемые PyQt widgets
  models/             pure Python state/data models
  adapters/           adapters для core/build/diagnostic planning
```

Qt-specific classes должны оставаться рядом с UI layer. Core inventory, build-plan generation и safety/privilege planning должны оставаться pure Python, чтобы их можно было тестировать без display server.

## Правило языка документации

Активная проектная документация ведётся на русском языке. Исключение — vendored upstream-документация внутри `core/zapret2/docs/`, потому что она относится к импортированному ядру и должна сохраняться как source input.
