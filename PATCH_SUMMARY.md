# v0.4-alpha Stage 4 — Discord hostlist/runtime alignment

Этот devctl-патч выравнивает Discord service target preset с тем hostlist, через
который Default workflow запускает выбранную strategy.

## Реализация

- `profiles/hostlists/default.hosts` дополнен Discord desktop non-voice entries:
  - `gateway.discord.gg`;
  - `cdn.discordapp.com`;
  - `media.discordapp.net`.
- YouTube baseline entries оставлены в default hostlist.
- В `service_targets.py` добавлены helper-ы для сравнения service target preset-ов
  с hostlist text: parser hostlist, нормализация URI-like targets и поиск
  missing entries.
- Добавлен тестовый contract, что `youtube-basic` и `discord-desktop` покрыты
  `profiles/hostlists/default.hosts`.
- Runtime apply plan проверяется на использование того же aligned hostlist.

## Граница stage

Патч не вводит service auto-switching, не меняет Strategy export metadata, не
добавляет Discord voice/UDP и не обещает одновременную работу YouTube и Discord.
Следующая стадия цикла — service-aware export и Strategy UX.
