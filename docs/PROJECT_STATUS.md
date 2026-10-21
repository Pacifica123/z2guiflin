# Фактический статус v1.1

Текущая версия — **1.3.0**: DNS-каталог и смена DNS, удобная страница «Пресеты» (порядок, пересечения профилей, «Кто сработает первым?», исключения, массовое удаление), Tor отдельной страницей с мостами и автообновление. 1.2.0 — навигация по пути пользователя, витрина «Главная», подсказки «Что попробовать» после вердикта сети. Правило версий — [VERSIONING.md](VERSIONING.md). Ниже — статус v1.1, на котором 1.2.0 и 1.3.0 основаны.

v1.0 закрыта по явному решению владельца проекта 01.10.2026. Приложенный implementation snapshot a0bd474 ещё содержит label 1.0.0rc7; новая product version — **1.1.0 / v1.1**. Это зафиксированное решение о выпуске, без выдумывания отсутствующих network/VM/review receipts.

v1.1 исправляет ложный баннер VLESS при выборе только Zapret, отсутствие provenance gate в composer readiness, неверное следующее действие Overview и невидимые checkbox indicators. Сборка доступна в обычном Overview; VLESS inputs показаны только при выборе VLESS. Автор может создать package inputs непосредственно из checkout; README указывает точный cwd makepkg.

История: 0.8.0, P04 закрыт (P04a, P04b, P04c, P04d), READY_FOR_USE_WITHIN_P04D; P05 discovery/help/health и P06 packaging сохранены. P07 PC/profile/freeze остаются историческими. Current source freeze v1.1 отделён от P07, tests и owner observations по-прежнему имеют собственные scope/time/environment. Ни current all-green, ни решение о версии не являются доказательством универсальной доступности VLESS/Vesktop.

[Контракт v1.1](developer/V11_PATCH_CONTRACT.md) · [Установка](user/getting-started.md) · [Диагностика](operations/troubleshooting.md).

Исторический P03: v0.7, READY_FOR_USE_WITHIN_P03; его marker описывает принятие своего snapshot и не заменяет проверку нового бинарника.
