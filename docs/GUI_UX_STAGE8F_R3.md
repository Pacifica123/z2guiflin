# v0.4-alpha Stage 8f-r3 — theme toggle и финальная компоновка

## Причина

Owner-run Stage 8f-r2 показал четыре оставшихся UX-дефекта:

- заголовки `QGroupBox` всё ещё выглядели как выделенные маркером;
- `QTabBar` рисовал системную base-line над содержимым;
- правая колонка действий Blockcheck Lab обрезала подписи;
- страница настроек оставалась placeholder-ом.

## Исправление

Stage 8f-r3:

- делает фон `QGroupBox::title` полностью прозрачным;
- отключает `QTabBar` base-line одновременно через QSS и `setDrawBase(False)`;
- перестраивает Actions Blockcheck Lab в устойчивую двухколоночную сетку;
- добавляет страницу настроек с painted toggle светлой/тёмной темы;
- сохраняет выбранную тему в `QSettings` и применяет её до создания главного окна;
- добавляет отдельную тёмную pastel palette и QSS без зависимости от desktop theme.

## Граница патча

Переключатель затрагивает только отображение. Runtime, Blockcheck execution,
HAR, стратегии, tunnel core, nftables, systemd и privilege boundary не меняются.
