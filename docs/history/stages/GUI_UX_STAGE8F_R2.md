# v0.4-alpha Stage 8f-r2 — финальная шлифовка GUI UX

## Причина

После Stage 8f-r1 тема стала предсказуемой, но owner-run показал ещё несколько
локальных UX-шероховатостей:

- warning-banner мог оставаться на экране после смены компонентного выбора;
- нижние кнопки под таблицей `Overview` визуально наезжали на последние строки;
- `QTabWidget` рисовал длинную горизонтальную линию над содержимым вкладок;
- `QGroupBox` оставлял слишком контрастный фон у title-notch;
- `QSpinBox` и часть action-кнопок выглядели нативно-жёстко и местами обрезали текст.

## Исправление

Stage 8f-r2 делает только точечную UX-шлифовку:

- плашка launch issue очищается при смене selected components и при изменении пути к core binary;
- кнопки копирования в `Overview` перенесены над таблицей;
- для `QTabWidget::pane` убрана лишняя линия/рамка;
- title-background у `QGroupBox` приведён к цвету поверхности страницы;
- spinbox up/down buttons получили явный pastel style;
- кнопки Action в Blockcheck Lab теперь могут расширяться и меньше режут длинные подписи.

## Граница патча

Патч не меняет runtime, tunnel logic, Blockcheck execution, HAR parsing,
стратегии, nftables, systemd или privilege boundary.
