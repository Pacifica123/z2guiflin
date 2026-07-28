# Patch summary

## Title

Финальная шлифовка GUI UX после owner-run

## Что изменено

- Launch issue banner теперь сбрасывается при смене selected components и пути к VLESS core.
- Кнопки копирования в `Overview` перенесены над таблицей и больше не перекрывают строки.
- У `QTabWidget` убрана лишняя горизонтальная линия над содержимым.
- `QGroupBox` title-notch стал мягче и не выбивается белыми углами.
- `QSpinBox` получил явный pastel-style для up/down button area.
- В Blockcheck Lab action-кнопки могут расширяться и лучше вмещают длинные подписи.

## Граница патча

Патч не меняет сетевую логику, стратегии, Blockcheck execution, HAR workbench,
tunnel runtime, nftables, systemd или privilege boundary.
