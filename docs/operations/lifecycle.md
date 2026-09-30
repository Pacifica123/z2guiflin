# Обновление, migration и удаление

Сначала остановите и откатите owned runtime штатным workflow. Обновление пакета выполняйте через pacman. На следующем запуске launcher проверит новый release manifest и installation receipt пользовательского workspace.

Если release digest не изменился, bootstrap идемпотентен. Если изменился, новая копия подготавливается во временном каталоге под тем же user data root. Managed copies обновляются только при совпадении старого recorded SHA-256 с текущими байтами. Изменённые файлы, неизвестные receipt schemas, symlink-конфликты и записи активного/stale runtime блокируют обновление без изменения данных. Пресеты, contexts, стратегии, темы и `.zap2` сохраняются; удалённые из нового пакета user-owned seeds также сохраняются.

После проверки workspace переключается атомарным rename; предыдущая копия остаётся в `~/.local/share/zap2gui/backups/` (или в выбранном XDG_DATA_HOME). Receipt содержит прежний и новый release digest. Ошибка публикации возвращает старую копию. Резервную копию не удаляют автоматически. Между двумя rename возможен сбой питания: если workspace отсутствует, но есть backups, запуск прекращается и требует явного восстановления выбранной копии; пустая новая установка не должна скрыть это состояние.

Изменение resource generation не повышает старый core build receipt до verified: после обновления provenance проверяется снова и при необходимости требуется новый build plan. Не переносите live session между workspace. Импорт существующего checkout state не выполняется автоматически; новый installed workspace создаётся отдельно, а перенос пресетов выполняют явными штатными import/export действиями.

Перед удалением пакета остановите session и revert owned rules, пока helper доступен. Затем выполните `sudo pacman -R zap2gui-linux`. Пакетный менеджер удаляет только системные package-owned файлы. Пользовательский workspace, его backups и QSettings сохраняются. Автоматического удаления nft rules, процессов или пользовательских каталогов при uninstall нет.

[Первые действия](../user/getting-started.md) · [Архитектура](../developer/architecture.md).
