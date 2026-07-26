# Patch summary

## Title

Ввести архитектуру «пресет → упорядоченные traffic-профили»

## Что изменено

- Добавлена чистая модель `ZapretPreset`, `TrafficProfile`, `TrafficFilter` и
  `PresetAction`.
- Все существующие runtime args вынесены в канонические
  `presets/workspace/*.txt` без изменения порядка или значений.
- Strategy JSON теперь содержит `presetPath` и остаётся metadata-слоем.
- Загрузчик проверяет полное совпадение `.txt` и legacy `runtimeArgs`.
- Blockcheck exporter создаёт одновременно generated JSON metadata и `.txt`
  preset.
- Вкладка `Стратегии` заменена каталогом `Пресеты` с таблицей profile order,
  filter, strategy, range и direction.
- Добавлены CLI `--list-presets`, `--show-preset`, `--show-preset-profile` и
  `--select-preset`.
- Старые strategy/profile имена оставлены как совместимые алиасы.

## Безопасность

Патч не меняет nftables, NFQUEUE, systemd, sudo-askpass и порядок runtime
lifecycle. Round-trip тесты требуют, чтобы разобранный пресет собирался в точно
тот же argv, который использовался до изменения архитектуры.
