# P06 — документация и воспроизводимая дистрибуция, RC6

Текущий продукт: 0.10.0rc6, кандидат P06 по плану 0.9→0.10. Финальное принятие требует полного подтверждения чистого Arch lifecycle; последняя независимая финальная опора — 0.8.0. Входной post-P05 snapshot ca6b4fb сохранён в PRE; новый owner receipt не выдуман.

Текущая документация отделена от побайтно сохранённой истории. Генерируемый справочник берёт действия, CLI, operand bindings, понятия, схемы, capability predicates и provenance из исполняемых источников. Системный package-owned код и helper работают с отдельным пользовательским compatibility workspace. Receipt, conflict gate и backups сохраняют пользовательские данные; uninstall удаляет только системные package-owned файлы. Service unit остаётся plan-only. About разделяет идентификаторы; support экспортирует только разрешённые поля и хеши чувствительных идентификаторов.

Release строится из явного списка файлов, с одинаковыми tar/gzip metadata и закреплённым SHA256 в PKGBUILD. Единый профиль devctl и shell: `bash meta_tools/hyperpatch_acceptance.sh --p06`, с полными логами и ZIP результата. Дополнительный VM recorder выполняет установленный launcher вне checkout и записывает ручные фактические проверки runtime/GUI/диагностики, настоящий upgrade и сохранение данных при удалении.

Канонические 119 ActionContract, 117 legacy selectors, dispatcher, P03 generation и замороженные исторические receipts сохранены. Подробная контейнерная проверка находится в отдельном evidence приложении devctl-патча; она не подменяет owner host acceptance.
