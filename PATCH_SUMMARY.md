# Patch summary

v0.4 maintenance: удаление owner-managed preset и общий source package root resolver.

- Во вкладке `Пресеты` появилась отдельная кнопка `Удалить пресет`; `Удалить профиль` теперь однозначно относится только к строке profile.
- Удалять можно только owner-managed presets. Reference/community presets остаются read-only.
- Удаление снимает canonical `.txt`, metadata JSON и запись из `strategies/catalog.json`.
- Если preset был выбран, selection безопасно переключается на catalog default до удаления. Запущенный выбранный preset по-прежнему защищён runtime guard.
- `presets/imported-assets/*` удаляется только если больше ни один preset на тот же asset root не ссылается.
- Поиск companion files вынесен в `import_source_root.py`: resolver не знает о preset/TXT и работает с любым source file + безопасными relative refs.
- Автопоиск source package root проходит до 10 ancestors и поэтому находит корень для вложенности `presets/builtin/winws2/...`.
- Распознаётся layout проекта loop-uh: source resource root `<repo>/src` и packaged application root с соседними `presets/`, `lists/`, `lua/`, `bin/`.
- GUI показывает auto-detected root, причину и coverage; ручной выбор root стартует с этого кандидата.
- Исходный `zapretgui.zip` проверен отдельно: для `src/presets/builtin/winws2/Universal V5.txt` root определяется как `src`, профилей 37/actions 55, но coverage runtime lists = `0/37`, потому что source checkout не содержит соответствующие `lists/*.txt`. Это не маскируется: нужен installed/extracted runtime root или другой пакет, реально содержащий файлы.
