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
