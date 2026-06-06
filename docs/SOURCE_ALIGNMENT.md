# Выравнивание с источниками — v0.3-alpha_stage_3

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
