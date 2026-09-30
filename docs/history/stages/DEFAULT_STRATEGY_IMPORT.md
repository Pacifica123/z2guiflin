# Импорт Default strategy из Windows GUI

Начиная с `v0.3-beta_stage_4` проект переносит первую базовую стратегию из Windows GUI: `Default v1 (game filter)`.

Источник найден в архиве Windows GUI по пути:

```text
src/presets/builtin/winws2/Default v1 (game filter).txt
```

В Windows GUI это выбранный по умолчанию preset для режима `zapret2_mode` / `winws2`. Это подтверждается константой `DEFAULT_PRESET_FILE_NAME_BY_ENGINE` в `src/settings/mode.py`, где для `ENGINE_WINWS2` указан файл `Default v1 (game filter).txt`.

## Что перенесено

Перенос намеренно частичный:

- оригинальный preset сохранён как reference в `strategies/imported/windows-default-v1-game-filter.txt`;
- машинная сводка по preset сохранена в `strategies/imported/windows-default-v1-game-filter.json`;
- `strategies/manual-local.json` получил блок `sourcePreset` и минимальные `runtimeArgs` для `nfqws2`;
- `profiles/hostlists/default.hosts` больше не пустой: он содержит seed-домены из основных веток Default preset.

## Что не перенесено напрямую

Полный Windows preset не исполняется в Linux runtime как есть. Причины:

- параметры `--wf-*` относятся к WinDivert и не являются Linux runtime interface;
- часть веток использует `ipset`-файлы, которых пока нет в нашем workspace;
- часть blob-файлов Windows GUI не импортирована в Linux core tree;
- полный preset содержит много профилей, которые нужно переносить и проверять отдельно.

Поэтому Stage 4 переносит только минимальный мост: Default-source, default hostlist seed и базовые Lua-аргументы, совместимые с `nfqws2`.

## Аргументы runtime

Минимальная Linux-версия использует upstream Lua-файлы из vendored core:

```text
--lua-init=@core/zapret2/lua/zapret-lib.lua
--lua-init=@core/zapret2/lua/zapret-antidpi.lua
```

Дальше задаётся базовая обработка HTTP/TLS через встроенные fake blobs и `multisplit`. Эти параметры хранятся в `strategies/manual-local.json`, а session runner добавляет их в args-файл перед `--hostlist`.

## Политика hostlist

`profiles/hostlists/default.hosts` — это seed, а не претензия на полный список Windows GUI. Файл должен оставаться owner-maintained: владелец может расширять его вручную, а будущие патчи могут добавлять отдельные импортируемые hostlist/ipset слои.

## Политика отладки

Предыдущие runtime-тесты показали, что `--debug=@...` быстро создаёт десятки мегабайт per-packet логов. Поэтому с этого stage debug выключен по умолчанию. Для локальной диагностики можно включить его через переменную окружения:

```bash
ZAP2_RUNTIME_DEBUG=1 PYTHONPATH=gui python -m zap2_gui.app --default-start --confirm runtime-default-manual-local-default-start-workflow-plan
```

Это не меняет plan/confirmation модель, но делает логирование явно выбранным действием владельца.
