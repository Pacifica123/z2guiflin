# Контракт патча P07: compositional qualification RC7

Тезис: текущие контракты P01–P06 проверяются совместно относительно замороженного кандидата, gates G01–G21 и обязательных сценариев J1–J7. Новая архитектура и расширение сетевой поддержки в этот этап не входят. База — предоставленный snapshot 65b60b2; кандидат 1.0.0rc7, целевой final 1.0.0 назначается только после всех MUST PASS и независимого review.

Инварианты: immutable Plan/hash/confirmation, bounded package-owned helper, foreign resources survive, неизвестные схемы и downgrade не меняют пользовательские данные, product/schema/upstream/core/evidence различаются, HTTP не повышает приложение, нет автоматических nft/network mutations в --p07. Полный корпус не сокращается из-за среды. Архив без живых данных/секретов. Результаты по partitions не сворачиваются в ложный all-green.

Фальсификаторы и конкретные probes опубликованы в [p07-contract.json](p07-contract.json). Criterion weakening требует отдельного SA с новым доказательством. Scope не сужен для обхода отсутствующего live receipt. Голос, TUN, сервисный автозапуск и все transport/core combinations не обещаются как v1 supported.

Изменения ограничены квалификацией, текущей документацией, версией кандидата и выявленными локальными исправлениями P06. Baseline ActionContract/dispatcher/app/helper/upstream authority сохраняются. Проверяемые evidence связываются с source digest, PC digest, release digest, profile digest и временем/средой. Повторный запуск после любого изменения требует новой привязки.

Data migration: новые qualification artifacts не принимаются за runtime state. P06 schema1 сохраняется; same-release bootstrap разрешён при активном runtime, настоящее обновление по-прежнему требует stop/reconcile. Downgrade старой версии workspace запрещён без явного восстановления резервной копии. Никакое старое confirmation не повышается по новой версии.

Rollback: откатить файлы патча на входной snapshot; пользовательский workspace и backups не удалять. Package downgrade не смешивать со state downgrade; используйте отдельный data root либо явно выбранную согласованную backup. При broad architectural defect qualification останавливается и проблема возвращается владельцу области.

Review порядок: PC и frozen inventory → diff → полные evidence/logs → support/migration matrix → SA → только затем narrative. Самостоятельный reviewer читает отдельный deliberate-failure support artifact и проверяет actionability/redaction. Поле PASS в JSON без артефакта и точной привязки не считается достаточным. Owner receipts являются локальными attestations, не криптографическим удостоверением истины.

После исправления SA-P07-03 `--p07` является check применения RC (freeze/projections/полный L0–L2); `--p07-release` является строгой финальной квалификацией по всем G01–G21/J1–J7. Оба режима используют один runner и сохраняют полную matrix. Owner предыдущий RC7: 651/651 tests PASS, qualification BLOCKED без receipts; это историческое наблюдение, а не PASS нового freeze.
