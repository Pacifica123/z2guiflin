# v0.4-alpha Stage 8f-r1 — нормализация светлой темы

## Причина

После owner-run Stage 8f выяснилось, что одного application QSS недостаточно.
На рабочем столе с тёмной системной палитрой часть Qt-виджетов продолжала брать
цвета из desktop theme. Из-за этого таблицы, списки и фон Blockcheck Lab становились
почти чёрными, хотя окружающий shell уже был светлым.

## Исправление

Stage 8f-r1 добавляет явную светлую `QPalette` перед применением QSS. Палитра
задаёт базовые цвета для окна, текста, полей, alternate rows, кнопок, selection,
placeholder и disabled state. Это отсоединяет Fusion widgets от тёмной палитры
KDE/GNOME и делает результат одинаковым на разных Arch-based desktop sessions.

Дополнительно QSS явно фиксирует фон и selection для:

- `QTableView`, `QTreeView`, `QListView` и их viewport;
- popup-списков `QComboBox`;
- header/corner sections;
- disabled полей и вкладок;
- горизонтальных scrollbars.

## Blockcheck Lab

Локальный стиль Blockcheck больше не использует светло-серый текст, рассчитанный
на тёмный фон. Кнопки `Tournament`, `Checklist` и `Endpoints` получили по половине
ширины строки вместо четырёх слишком узких колонок.

## Граница патча

Патч не меняет Blockcheck execution, HAR workbench, стратегии, runtime, tunnel,
nftables, systemd или privilege workflow. Это только исправление рендера и
компоновки действий.
