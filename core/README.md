# Область исходников ядра

`core/zapret2/` содержит vendored-снимок upstream-дерева `zapret2` из архива, переданного для перезапуска v0.3-alpha.

Правила для этой директории:

1. Держать upstream-исходники механически отделёнными от нашего GUI-кода.
2. Не запускать upstream installer scripts из проверок, сгенерированных ассистентом.
3. Будущие обновления upstream оформлять как явные source-import patches с манифестом и заметками для ревью.
4. Не добавлять скомпилированные бинарные артефакты в Git, пока владелец явно не примет другое решение.

Лицензия upstream сохранена в `core/zapret2/docs/LICENSE.txt`.

Служебные файлы Stage 4 внутри `core/zapret2/`:

- `UPSTREAM_IMPORT.json` и `UPSTREAM_IMPORT.md` — исходный манифест импорта;
- `CORE_INVENTORY.json` — read-only снимок состава ядра;
- `BUILD_MAP.json` — карта Makefile, targets и будущих build units.

`CORE_INVENTORY.json` и `BUILD_MAP.json` относятся к нашему слою метаданных. Они не являются upstream-кодом и не запускают сборку.
