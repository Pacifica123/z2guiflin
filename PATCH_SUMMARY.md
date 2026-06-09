# v0.4-alpha Stage 3 — Blockcheck Lab preset selector

Этот devctl-патч подключает registry service target presets к пользовательскому
Blockcheck path.

## Реализация

- В Blockcheck Lab добавлен selector `Service target`.
- `YouTube basic` и `Discord desktop non-voice` автозаполняют поле доменов из
  registry и показывают его как read-only preset-owned значение.
- `Custom manual targets` оставляет ручной ввод, проходит прежнюю валидацию и
  запоминает последнюю ручную строку при переключении preset-ов.
- CLI получил `--blockcheck-target-preset`.
- `--blockcheck-domains` теперь работает как явный custom override.
- `--blockcheck-target-preset custom` без `--blockcheck-domains` возвращает
  понятную ошибку.

## Граница stage

Патч не меняет runtime apply, nftables, hostlist и Strategy export metadata.
Следующая стадия цикла — Discord hostlist/runtime alignment.
