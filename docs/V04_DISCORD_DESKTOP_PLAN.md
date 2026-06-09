# План v0.4-alpha: desktop Discord

`v0.4-alpha` открывает цикл после owner-declared `v0.3-stable`. Предыдущая веха доказала, что проект уже может провести пользователя по цепочке:

```text
Blockcheck lab -> AVAILABLE strategies -> generated strategy files -> выбор стратегии -> Default workflow -> рабочий YouTube
```

Цель `v0.4-*` — повторить эту цепочку для desktop-версии Discord.

## Исходная позиция

На момент открытия `v0.4-alpha` уже есть:

- vendored `zapret2` в `core/zapret2/`;
- локальная сборка `nfqws2` и `mdig` через owner-controlled build path;
- live Blockcheck lab без заморозки GUI;
- статистика длинных прогонов;
- sequential target candidates и dead-target guard;
- экспорт `AVAILABLE` стратегий в `strategies/generated/`;
- вкладка `Стратегии` с выбором active strategy для Default profile;
- owner-confirmed Default workflow через plan/hash/confirmation/sudo-askpass.

## Цель цикла

Минимальная полезная цель `v0.4-alpha`:

1. подобрать candidate targets для desktop Discord;
2. прогнать их через Blockcheck lab без бессмысленного зависания на мёртвом target;
3. получить хотя бы одну generated strategy для Discord;
4. выбрать её во вкладке `Стратегии`;
5. запустить Default workflow;
6. проверить, что desktop Discord оживает в окружении владельца.

## Нефокус v0.4

Для `v0.4-*` сознательно откладывается задача автоматического объединения стратегий нескольких сервисов. Допустимый пользовательский сценарий:

```text
выбрать YouTube strategy
или
выбрать Discord strategy
```

Недопустимо тратить цикл на обязательное решение задачи:

```text
автоматически совместить YouTube + Discord + будущие сервисы в одну универсальную стратегию
```

Такое объединение лучше делать позже, когда будут понятны реальные Discord probes, порты, протоколы и конфликты `nfqws2` аргументов.

## Методология

Для Discord не нужно сразу добавлять скрытый «магический режим». Предпочтительный путь:

- явно показывать candidate targets владельцу;
- сохранять live output и successful source logs;
- экспортировать Discord strategies с service-aware именами;
- сохранять возможность открыть JSON и увидеть исходную `nfqws2` строку;
- не менять firewall/service state без того же owner-confirmed workflow, который уже используется для YouTube.


## Stage 1 roadmap уточнение

`v0.4-alpha_stage_1` уточняет цель цикла: финальный результат `v0.4-*` — это
осознанный выбор между сервисными целями YouTube и Discord, а не обязательное
создание одной стратегии, которая гарантированно оживляет оба сервиса
одновременно.

Для первого практического Discord-прохода принимается non-voice гипотеза:
достаточно дать Blockcheck lab готовый Discord target preset и затем убедиться,
что runtime hostlist содержит те же targets. Минимальный seed:

```text
discord.com gateway.discord.gg cdn.discordapp.com discordapp.net discord.media media.discordapp.net updates.discord.com discord.gg
```

После подтверждения non-voice слоя можно отдельно решать, входит ли Discord
voice/UDP в текущую веху или переносится на следующий цикл. Подробная
последовательность патчей описана в `V04_ALPHA_PATCH_ROADMAP.md`.

## Stage 2 registry уточнение

`v0.4-alpha_stage_2` добавляет `gui/zap2_gui/models/service_targets.py` —
центральный registry для service target presets. Он фиксирует `youtube-basic`,
`discord-desktop` и `custom`, но пока не меняет runtime apply и не добавляет GUI
selector. Default Blockcheck остаётся YouTube-oriented, а Discord seed становится
доступен как кодовый preset для следующего stage.



## Stage 3 selector уточнение

`v0.4-alpha_stage_3` выводит `youtube-basic`, `discord-desktop` и `custom` в
Blockcheck Lab selector и CLI `--blockcheck-target-preset`. Теперь первый
Discord non-voice прогон можно начать без ручного набора длинной строки доменов:
выбрать `Discord desktop non-voice`, оставить HTTPS TLS1.2/TLS1.3/HTTP3 enabled
и запустить sequential Blockcheck candidates.

Важно: Stage 3 пока отвечает только за target discovery UX. Runtime hostlist ещё
не синхронизирован с Discord seed, поэтому найденная Discord strategy не считается
полностью готовой к owner verification до Stage 4.

## Stage 4 hostlist/runtime alignment

`v0.4-alpha_stage_4` делает первый Discord runtime path воспроизводимее:
`profiles/hostlists/default.hosts` теперь покрывает тот же `discord-desktop`
non-voice seed, который выбирается в Blockcheck Lab. Добавлены особенно важные
entries для desktop-клиента:

```text
gateway.discord.gg
cdn.discordapp.com
media.discordapp.net
```

Это не включает voice/UDP и не меняет смысл Default workflow. Runtime по-прежнему
запускает одну выбранную strategy через owner confirmation, но hostlist больше не
расходится с Discord targets, по которым была найдена generated strategy.

## Признаки готовности к v0.4-beta

`v0.4-alpha` можно считать готовой к переходу в beta, когда владелец сможет сказать:

- GUI предложил или позволил задать осмысленные Discord targets;
- Blockcheck нашёл применимую стратегию для одного из них;
- стратегия экспортировалась в `strategies/generated/`;
- стратегия была выбрана во вкладке `Стратегии`;
- Default workflow стартовал без регресса safety boundary;
- desktop Discord реально заработал хотя бы в базовом сценарии владельца.
