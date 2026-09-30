# Версионирование v1.1

v1.0 закрыта по явному решению владельца проекта 01.10.2026. Приложенный implementation snapshot a0bd474 ещё содержит label 1.0.0rc7; новая product version — **1.1.0 / v1.1**. Это зафиксированное решение о выпуске, без выдумывания отсутствующих network/VM/review receipts.

v1.1 исправляет ложный баннер VLESS при выборе только Zapret, отсутствие provenance gate в composer readiness, неверное следующее действие Overview и невидимые checkbox indicators. Сборка доступна в обычном Overview; VLESS inputs показаны только при выборе VLESS. Автор может создать package inputs непосредственно из checkout; README указывает точный cwd makepkg.

История: 0.8.0, P04 закрыт (P04a, P04b, P04c, P04d), READY_FOR_USE_WITHIN_P04D; P05 discovery/help/health и P06 packaging сохранены. P07 PC/profile/freeze остаются историческими. Current source freeze v1.1 отделён от P07, tests и owner observations по-прежнему имеют собственные scope/time/environment. Ни current all-green, ни решение о версии не являются доказательством универсальной доступности VLESS/Vesktop.

[Контракт v1.1](developer/V11_PATCH_CONTRACT.md) · [Установка](user/getting-started.md) · [Диагностика](operations/troubleshooting.md).

Product version, upstream bol-van version, schema version и external core version независимы. Version 1.1.0 не повышает автоматически receipt чужой generation до verified.

Исторический P03: v0.7, READY_FOR_USE_WITHIN_P03; его marker описывает принятие своего snapshot и не заменяет проверку нового бинарника.
