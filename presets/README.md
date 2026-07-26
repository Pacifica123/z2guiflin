# Пресеты Zapret2

`presets/` — исполнимый слой настроек `nfqws2`.

Пресет хранится как `.txt` с теми же опциями, которые раньше лежали только в
`strategies/*.json -> runtimeArgs`. Порядок блоков принципиален: новый профиль
начинается после `--new`, а nfqws2 выбирает первый профиль, фильтр которого
подошёл трафику.

```text
presets/
  workspace/   проверенные, импортированные и owner-managed пресеты
  generated/   пресеты, созданные из результатов Blockcheck exporter
```

JSON в `strategies/` пока сохраняется как слой метаданных и совместимости:
название, назначение, источник, service target и safety contract. Поле
`presetPath` указывает на канонический `.txt`. Поле `runtimeArgs` временно
сохраняется как контрольная копия; загрузчик требует их полного совпадения.

GUI показывает структуру так:

```text
пресет -> упорядоченные профили -> filter / strategy / range / direction
```

Применение пресета по-прежнему проходит через существующие plan, confirmation,
sudo-askpass и runtime lifecycle. Само чтение каталога ничего не запускает.

## Конструктор

GUI может создавать новые owner-managed пресеты в `presets/workspace/`. Только
такие пресеты разрешено менять из конструктора. Для каждого профиля задаются
filter, target и strategy; порядок меняется кнопками `↑`/`↓`. Blockcheck может
вставить найденную domain HTTP/TLS/QUIC strategy прямо в профиль. Discord
Voice/STUN UDP требует отдельной диагностики.

Подробно: `docs/PRESET_CONSTRUCTOR.md`.
