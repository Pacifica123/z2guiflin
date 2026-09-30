# Текущая документация

Сначала читать [установку и первое безопасное действие](user/getting-started.md). Этот раздел описывает действующий кандидат продукта; хронология не является инструкцией по текущей установке. Старые адреса сохранены как явно подписанные переходы к оригинальным документам.

- [Понятия и границы действий](concepts/README.md)
- [Диагностика и восстановление](operations/troubleshooting.md)
- [Обновление и удаление](operations/lifecycle.md)
- [Архитектура и сборка пакета](developer/architecture.md)
- [Генерируемые контракты, CLI, схемы и возможности](generated/reference.md)
- [Статус проекта](PROJECT_STATUS.md), [версионирование](VERSIONING.md)
- [Upstream](upstream/README.md), [история](history/README.md)

Текущий кандидат: **1.0.0rc7 / v1.0 RC7**, этап P07. Финальная версия **1.0.0 не назначена**: G01–G21 и J1–J7 требуют текущих evidence partitions и независимого review. Вход — применённый post-P06 snapshot **65b60b2**. В нём нет новых owner receipts для native clean install/privilege/live VLESS/Vesktop; контейнерная приёмка P06 сохраняла BLOCKED. Историческая финальная опора — 0.8.0: P04 закрыт (P04a, P04b, P04c, P04d), `READY_FOR_USE_WITHIN_P04D`; P03 имеет исторический marker `READY_FOR_USE_WITHIN_P03`. Историческое принятие не переносится на текущий кандидат автоматически.

- [Квалификация и закрытие v1](operations/v1-qualification.md)
- [G01–G21 и J1–J7](generated/qualification.md)
- [Контракт патча](developer/P07_PATCH_CONTRACT.md) и [SA](developer/P07_SPEC_AMENDMENTS.md)
