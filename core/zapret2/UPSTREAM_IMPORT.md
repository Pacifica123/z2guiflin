# Заметки об upstream-импорте

Эта директория содержит vendored-снимок исходников, импортированный из `zapret2-core-from_bolvan.zip` для перезапуска `v0.3-alpha`.

- Upstream: `bol-van/zapret2`
- Импортировано файлов: `245`
- Исключено файлов: `9`
- Лицензия сохранена: `docs/LICENSE.txt`
- Content digest по импортированным файлам: `9d57e8fdee29938d560a390f976def49d4692f8dfda7e59c7df4a48fffe773d5`

Исключённые файлы — это CI metadata или compiled/binary artifacts из переданного upstream-архива. Они перечислены в `UPSTREAM_IMPORT.json`, чтобы будущий патч мог осознанно пересмотреть это решение.

GUI-слой должен считать эту директорию source input. Он не должен небрежно переписывать её и не должен выполнять installer scripts в рамках автоматической валидации.
