# Discord: Flowseal/Windows reference notes

Этот документ фиксирует исследовательские выводы Stage 7d по приложенным owner-архивам `zapret1-flowseal-windows.zip` и `zapret2-gui_windows.zip`. Он не является исполняемым preset-ом и не запускает Windows/WinDivert параметры на Linux.

## Что полезно для Linux v0.4

Flowseal-пакет показывает, что Discord обычно лечится не одной строкой, а несколькими слоями:

- общий TCP/HTTPS hostlist для `discord.com`, `discordapp.net`, `discord.media` и родственных доменов;
- отдельная обработка `discord.media` на альтернативных HTTPS-портах `2053,2083,2087,2096,8443`;
- отдельный UDP слой для voice/STUN, который для v0.4 non-voice пока остаётся вне критерия успеха;
- `stable.dl2.discordapp.net` лежит рядом с Google-like download/CDN обработкой, а не обязательно в том же слое, что `updates.discord.com`.

Windows GUI reference подтверждает похожую мысль: `updates.discord.com`, `discord.com`, `discord.media` и Discord UDP/voice представлены отдельными профилями. Поэтому Linux-проект не должен считать один домен `discord.com` доказательством полного desktop Discord coverage.

## Что нельзя переносить напрямую

Flowseal/Windows аргументы `winws.exe`, `--wf-*`, `--dpi-desync-*`, WinDivert filters, Windows service wrapper и бинарные blob-файлы не являются прямым Linux runtime API этого проекта. Для Linux-пути нужны либо:

- blockcheck-generated `nfqws2 --lua-desync=...` стратегии;
- либо отдельный вручную портированный `nfqws2`/Lua-compatible reference profile с явным owner review;
- либо будущий profile composition слой, где updater/app/gateway/CDN/voice могут иметь разные стратегии.

## Практическое следствие для Stage 7d

Port precheck не должен быть окончательным судьёй для Discord ordered phases. `stable.dl2.discordapp.net` уже давал `AVAILABLE`, но позднее был остановлен как `dead-target` из-за одного неудачного `nc`. Поэтому для `discord-desktop` GUI использует `dead-target guard: observe-only`: портовый precheck остаётся evidence, но стратегия всё равно проверяется.

## Следующий исследовательский слой

После Stage 7d логично отдельно делать не UX-патч, а настоящий record-holder validator:

1. найти одну стратегию на первой фазе;
2. материализовать её в one-strategy custom list;
3. проверить ту же стратегию на следующей фазе;
4. если она провалилась, пометить её непрошедшей и искать следующий candidate;
5. сохранять только record-holder и небольшой список прошлых рекордсменов.

Это отличается от target coverage scan и должно реализовываться как отдельный слой, чтобы GUI, пользователь и blockcheck не путали “какой-то домен дал AVAILABLE” с “одна стратегия прошла цепочку Discord desktop”.
