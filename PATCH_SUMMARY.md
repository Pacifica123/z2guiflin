# Patch summary

v0.4 stage8j: hot-swap пресетов, пользовательские темы, нативный каталог strat_collection и быстрый поиск.

- Клик по preset теперь может сразу применить его. При выключенном Default меняется только selection; при запущенном Default выполняется `stop -> select -> start` через существующий plan/confirmation/sudo-askpass workflow.
- Hot-swap транзакционный: не меняет selection при неудачном stop; при неудачном старте нового preset восстанавливает старый selection и делает одну попытку вернуть старый runtime.
- Режим одного клика включён по умолчанию и отключается в настройках. Кнопка `Применить пресет` остаётся явным ручным действием.
- Добавлен live-search по presets с `Ctrl+F`, по модели быстрого поиска из loop-uh GUI. Один запрос фильтрует локальные Zapret2 presets и встроенный strat_collection.
- Оформление вынесено в portable theme profile schema v1: семантические цвета, шрифт, размер, скругление и ширина navigation rail. Профиль применяется сразу, хранится в QSettings и импортируется/экспортируется в JSON.
- Добавлены `themes/example-custom.json` и русская инструкция `docs/CUSTOMIZATION.md` с форматом «создай собственную тему».
- Весь переданный strat_collection встроен в `presets/collections/strat_collection` и индексируется через `strag.json`: 55 стратегий, metadata, ports/hostlists, desync modes, исходные winws args и companion-file diagnostics.
- `.bat`/`winws.exe` из strat_collection являются только read-only источником анализа. Windows-команды не исполняются; автоматический zapret1 -> nfqws2 перевод запрещён, чтобы не выдавать приблизительную конверсию за рабочий Zapret2 preset.
- Добавлен stage8j test contract для hot-swap ordering/rollback, JSON themes, strat_collection indexing и GUI wiring.
