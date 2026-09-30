# Zap2 GUI Linux — v1.0 RC7 (P07 candidate)

GUI PyQt6 управляет zapret2, immutable execution Plan, owned runtime и диагностикой сетевых возможностей. Он предоставляет не универсальную стратегию и не обещает работоспособность по одному HTTP ответу, локальному listener или наличию процесса. Доступность зависит от сети, core, приложения и доказательств конкретного запуска.

Текущий кандидат: **1.0.0rc7 / v1.0 RC7**, этап P07. Финальная версия **1.0.0 не назначена**: G01–G21 и J1–J7 требуют текущих evidence partitions и независимого review. Вход — применённый post-P06 snapshot **65b60b2**. В нём нет новых owner receipts для native clean install/privilege/live VLESS/Vesktop; контейнерная приёмка P06 сохраняла BLOCKED. Историческая финальная опора — 0.8.0: P04 закрыт (P04a, P04b, P04c, P04d), `READY_FOR_USE_WITHIN_P04D`; P03 имеет исторический marker `READY_FOR_USE_WITHIN_P03`. Историческое принятие не переносится на текущий кандидат автоматически.

Начните с [установки](docs/user/getting-started.md), [текущей документации](docs/README.md) и [квалификации v1](docs/operations/v1-qualification.md). [Диагностика](docs/operations/troubleshooting.md), [обновление и удаление](docs/operations/lifecycle.md), [справочник](docs/generated/reference.md), [история](docs/history/README.md).

Поддерживаемый installation target — Arch-like Linux x86_64, локальный source release + SHA-pinned PKGBUILD + pacman. Installed GUI-код, resources и bounded root-helper принадлежат пакету; writable compatibility workspace — пользователю. Service unit не устанавливается: plan-only. Voice/media, TUN, все core/transport combinations не объявлены supported по bootstrap.

Применение кандидата devctl: `bash meta_tools/hyperpatch_acceptance.sh --p07` проверяет freeze, проекции и полный L0–L2 corpus. Финальная квалификация: `bash meta_tools/hyperpatch_acceptance.sh --p07-release` выполняет тот же pipeline и требует все G01–G21/J1–J7 partitions. Отсутствующая owner evidence сохраняет qualification BLOCKED и запрещает final v1; применение RC допускается при успешных проверках кандидата. Версия/tag автоматически не присваиваются.
