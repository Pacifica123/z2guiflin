# Patch summary

## Title

Нормализация светлой темы после owner-run

## Что изменено

- Добавлена явная светлая `QPalette`, не зависящая от тёмной темы KDE/GNOME.
- Таблицы, списки, popup-списки и их viewport получили фиксированный светлый фон.
- Selection, disabled state, headers и scrollbars приведены к одной палитре.
- Blockcheck Lab больше не рисует тёмный фон со светло-серым локальным текстом.
- Узкие кнопки `Tournament`, `Checklist` и `Endpoints` переразложены по две в ряд.
- Runtime status/banner цвета заменены на стабильные pastel hex values.

## Граница патча

Патч не меняет сетевую логику, стратегии, Blockcheck execution, HAR workbench,
tunnel runtime, nftables, systemd или privilege boundary.
