# Patch summary

## Title

Theme toggle и исправление остаточных UX-дефектов

## Что изменено

- Убран фон-маркер у заголовков `QGroupBox`.
- Над вкладками Tunnel и Logs отключена системная base-line.
- Actions в Blockcheck Lab переведены на устойчивую двухколоночную сетку без обрезки подписей.
- Страница `Настройки` получила сохраняемый переключатель светлой/тёмной темы.
- Добавлена отдельная тёмная pastel palette/QSS, применяемая до создания окна.

## Граница патча

Патч не меняет сетевую логику, runtime, Blockcheck execution, HAR workbench,
стратегии, tunnel core, nftables, systemd или privilege boundary.
