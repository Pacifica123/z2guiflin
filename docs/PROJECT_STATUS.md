# Фактический статус P07

Текущий кандидат: **1.0.0rc7 / v1.0 RC7**, этап P07. Финальная версия **1.0.0 не назначена**: G01–G21 и J1–J7 требуют текущих evidence partitions и независимого review. Вход — применённый post-P06 snapshot **65b60b2**. В нём нет новых owner receipts для native clean install/privilege/live VLESS/Vesktop; контейнерная приёмка P06 сохраняла BLOCKED. Историческая финальная опора — 0.8.0: P04 закрыт (P04a, P04b, P04c, P04d), `READY_FOR_USE_WITHIN_P04D`; P03 имеет исторический marker `READY_FOR_USE_WITHIN_P03`. Историческое принятие не переносится на текущий кандидат автоматически.

P07 добавляет candidate freeze, source/release/PC/profile binding, G01–G21/J1–J7 matrix и проверку typed owner artifacts. Локальные tests, privilegedOS, liveNetwork, targetApp, package, migration/provenance и review учитываются раздельно. PASS одной области не заменяет другую. Полный pytest corpus выполняется без исключения real-process fixtures; timeout завершает owned test process group и остаётся FAIL.

PRE выявил P06 defect: same-release bootstrap блокировал status/stop при активной session. Исправлен порядок проверок; upgrade-only stop/reconcile gate сохраняется. Второе уточнение — более старый пакет не перезаписывает более новый workspace без явного выбора совместимой backup/data root. Оба изменения записаны в SA, без ослабления MUST gates.

Support bundle сохраняет только разрешённые Plan/Run/log event projections и typed network Verdict; raw credentials, argv/config/source URI и raw logs не экспортируются. Independent actionability/redaction assessment остаётся обязательной отдельной evidence.

[Контракт патча](developer/P07_PATCH_CONTRACT.md), [SA](developer/P07_SPEC_AMENDMENTS.md), [справочник gates/journeys](generated/qualification.md) и [процедура закрытия](operations/v1-qualification.md) описывают текущие условия. Новые owner receipts не выдуманы; финальное повышение возможно только после полной успешной квалификации и review.

P05 discovery/help/health projection сохранён и проверяется вместе с P01–P06 contracts. Входной snapshot не содержит нового P05 owner receipt; текущая qualification не использует это отсутствие как разрешение ослабить gates.

После исправления SA-P07-03 `--p07` является check применения RC (freeze/projections/полный L0–L2); `--p07-release` является строгой финальной квалификацией по всем G01–G21/J1–J7. Оба режима используют один runner и сохраняют полную matrix. Owner предыдущий RC7: 651/651 tests PASS, qualification BLOCKED без receipts; это историческое наблюдение, а не PASS нового freeze.
