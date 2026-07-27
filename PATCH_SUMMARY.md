# Patch summary

## Title

Discord Voice source bridge и автоматический HAR workbench

## Что изменено

- Добавлены три альтернативных Discord Voice пресета для Linux/nfqws2:
  upstream conservative, Flowseal narrow и GUI Windows wide.
- Windows `wf-*` заменён существующим `capturePolicy`/nftables слоем; legacy
  `dpi-desync-*` не исполняется напрямую.
- Полный аудит voice-источников сохранён в
  `references/external/discord_voice_source_inventory.json`.
- HAR summary расширен безопасными `scheme`, HTTP version, L7/transport hints и
  обезличенными категориями ошибок.
- Добавлен HAR workbench: import, grouping, group target files,
  Blockcheck options и preset blueprint.
- Добавлены CLI и GUI-действия для HAR workbench и Discord Voice inventory.

## Граница автоматизации

Патч автоматически обрабатывает только локальные данные. Он не запускает
Blockcheck, не меняет nftables/systemd и не собирает исполняемый итоговый preset
до подтверждения стратегии для каждой обязательной группы.

HAR не используется для выбора Discord Voice: browser HAR не содержит реальный
UDP media-flow.
