# Явные уточнения P07 при повторном анализе

## SA-P07-01 — восстановить доступ к активному runtime на том же release

До: P06 ensure_workspace проверял active/stale session перед возвратом идемпотентного receipt, поэтому каждый новый installed CLI запуск status/stop завершался lifecycle error при активной session. Новое доказательство: воспроизводимый PRE bootstrap probe на неизменённом входе и отдельный regression fixture. После: проверка receipt/path/symlink остаётся, а same-release return выполняется до upgrade-only active gate. Настоящее обновление при активном/stale/unknown runtime остаётся запрещено. Причина — базовый lifecycle контракт должен позволять остановку собственного запуска. Владелец области P06; downstream G04/G15/J1/J3. Acceptance gates не ослаблены.

## SA-P07-02 — объявить и проверить downgrade policy

До: P06 имел неизвестную schema fail-closed, но не ограничивал переход на меньшую product version при известной schema1. После: распознаваемый более новый workspace не перезаписывается более старым пакетом; неизвестная версия требует явной migration. Пользователь выбирает совместимую backup либо отдельный data root. Новое доказательство — downgrade fixture с сохранением байтов до/после. Владелец области P06; downstream G06/J7. SemVer не заменяет schema, но является отдельным явным migration ограничением.

Поддержка сети и приложений не расширена и не сужена ради PASS. G01–G21 и J1–J7 остаются обязательными в опубликованном qualification profile. Отсутствующая owner/live/VM/review evidence блокирует final 1.0.0. Никакого SA, разрешающего заменить её контейнерными тестами, нет.

## SA-P07-03 — разделить применение RC и финальную квалификацию

Новый owner failed-архив: freeze, generated projections, 34 P07 fixtures и полный corpus 651/651 PASS; --p07 вернул 1 исключительно из-за отсутствующих owner partitions. Devctl откатил кандидат до создания фактического commit, необходимого G21. Это ошибка orchestration. Теперь --p07 допускает применение RC только после полного deterministic pipeline и валидного source freeze; --p07-release выполняет тот же pipeline и требует все G01–G21/J1–J7, owner receipts и независимый review. Matrix/qualificationResult/promotionAllowed сохраняются в обоих режимах. Ненулевой exit при test/freeze failure сохранён. Ни один финальный MUST criterion не изменён; final version/tag по-прежнему запрещены до полной квалификации. Старые owner receipts не переносятся на новый freeze.
