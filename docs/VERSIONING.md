# Версионирование квалификации

Текущий кандидат: **1.0.0rc7 / v1.0 RC7**, этап P07. Финальная версия **1.0.0 не назначена**: G01–G21 и J1–J7 требуют текущих evidence partitions и независимого review. Вход — применённый post-P06 snapshot **65b60b2**. В нём нет новых owner receipts для native clean install/privilege/live VLESS/Vesktop; контейнерная приёмка P06 сохраняла BLOCKED. Историческая финальная опора — 0.8.0: P04 закрыт (P04a, P04b, P04c, P04d), `READY_FOR_USE_WITHIN_P04D`; P03 имеет исторический marker `READY_FOR_USE_WITHIN_P03`. Историческое принятие не переносится на текущий кандидат автоматически.

Номинальный P07 переход — 0.10→1.0; выполненная работа пока обозначается 1.0.0rc7. Это версия кандидата, не свидетельство завершения gates. Историческая ступень v0.7, foundation P04a/P04b/P04c/P04d и final 0.8.0 остаются в immutable receipts.

Оси независимы: productSemVer, schemaName/schemaVersion, patch/stage lineage, vendored upstream 1.0.6, external core/app version, Plan/Run/Evidence IDs. Смена продукта не повышает core provenance, connection fidelity или capability verdict.

Закрытие: freeze candidate+PC+profile → выполненные L0–L5 и J1–J7 → артефакты привязаны к digest/time/env → все MUST PASS, без resolvable_blocking → независимый review(diff/evidence/SA) → отдельное присвоение 1.0.0/tag и сохранение финальных receipts. Отсутствующий receipt означает NOT_RUN; parser/core presence/process/localhost не являются сетевым доказательством.

Downgrade пользовательского workspace запрещён по меньшей product version даже при известной schema1. Это отдельная policy, а не смешение product и schema. Восстановление выполняется явно из согласованной backup либо в отдельном data root. Исторические receipts не меняются при новом product label.
