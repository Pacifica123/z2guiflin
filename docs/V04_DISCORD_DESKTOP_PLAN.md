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


## Stage 5 service-aware export и Strategy UX

`v0.4-alpha_stage_5` делает Discord Blockcheck результат owner-readable. При
запуске через `discord-desktop` выбранный service id попадает в сохранённый
Blockcheck plan/log, поэтому exporter больше не путает одиночный successful
candidate `gateway.discord.gg` с произвольным custom-доменом.

Generated Discord strategy получает service-aware id/title/metadata, например:

```text
blockcheck-discord-desktop-gateway.discord.gg-YYYYMMDD-HHMMSS-01
```

В Strategy UX теперь видно `Discord desktop non-voice (discord-desktop)`. Это не
полная готовность Discord path: следующий stage должен провести owner
verification loop — выбрать такую generated strategy, запустить Default workflow
и проверить desktop Discord non-voice в реальной среде.

## Признаки готовности к v0.4-beta

`v0.4-alpha` можно считать готовой к переходу в beta, когда владелец сможет сказать:

- GUI предложил или позволил задать осмысленные Discord targets;
- Blockcheck нашёл применимую стратегию для одного из них;
- стратегия экспортировалась в `strategies/generated/`;
- стратегия была выбрана во вкладке `Стратегии`;
- Default workflow стартовал без регресса safety boundary;
- desktop Discord реально заработал хотя бы в базовом сценарии владельца.


## Stage 6: owner verification loop

После Stage 5 Discord-generated strategies уже отличаются от YouTube-generated strategies по service label. Stage 6 добавляет проверочную петлю, которую владелец выполняет перед следующим патчем:

1. выбрать `Discord desktop non-voice` во вкладке Blockcheck lab;
2. прогнать sequential Blockcheck;
3. экспортировать `AVAILABLE` стратегии;
4. выбрать generated Discord strategy во вкладке `Стратегии`;
5. запустить Default workflow через существующий owner-confirmed путь;
6. полностью перезапустить desktop Discord;
7. заполнить `.zap2/verification/discord-non-voice-owner-check.md`.

Критерий Stage 6 — не «починить всё», а получить честный owner report: login/session, gateway, чаты и CDN/media работают или нет. Voice/UDP, звонки и screen share не входят в non-voice успех и не должны смешиваться с выводами Stage 7.
## v0.4-alpha Stage 7: failure-driven target coverage

`v0.4-alpha_stage_7` меняет акцент после первой личной проверки владельца: найденные `AVAILABLE` стратегии для `discord.com` оказались полезным сигналом, но не доказали прохождение desktop Discord updater. Поэтому Stage 7 добавляет evidence-first coverage loop.

Главные изменения:

- `discord-desktop` preset расширен target-ом `stable.dl2.discordapp.net`, который относится к updater/download layer.
- Blockcheck options получили candidate scan mode:
  - `stop-after-first-available` — удобен для уже подтверждённого YouTube baseline;
  - `scan-all-targets` — default для `discord-desktop`, потому что desktop Discord состоит из updater, app/API/gateway и CDN/media слоёв;
  - `skip-dead-targets-only` — сохраняет старую осторожную модель перехода только после dead-target evidence.
- GUI Blockcheck Lab получил selector `Candidate mode` и кнопку `Coverage`.
- Каждый single-candidate run сохраняется в `.zap2/blockcheck/logs/candidates/`.
- Per-target manifest `.zap2/blockcheck/logs/candidates/coverage-manifest.json` показывает status для каждого target: `available`, `unavailable`, `dead-target`, `unknown` или `not-tested`.
- Export generated strategies теперь берёт AVAILABLE candidate logs из coverage manifest и кладёт coverage snapshot прямо в strategy JSON.
- Strategy UX показывает coverage summary, чтобы `discord.com`-only успех больше не выглядел как подтверждение всего Discord desktop path.

Новый owner-facing диагностический контур:

```bash
PYTHONPATH=gui python -m zap2_gui.app --blockcheck-plan \
  --blockcheck-target-preset discord-desktop \
  --blockcheck-scan-mode scan-all-targets

PYTHONPATH=gui python -m zap2_gui.app --blockcheck-coverage
PYTHONPATH=gui python -m zap2_gui.app --blockcheck-export-strategies
```

Ключевой критерий после Stage 7: если desktop Discord зависает на `Checking for updates`, сначала смотреть coverage по `updates.discord.com` и `stable.dl2.discordapp.net`, а не считать любую стратегию для `discord.com` достаточной.

## v0.4-alpha Stage 7a — service coverage policy/tournament

Stage 7a добавляет универсальный слой service coverage policy поверх target presets. Теперь registry явно различает:

```text
any-target-available — достаточно одного рабочего target, например youtube-basic
maximize-targets — порядок не важен, но нужно максимальное покрытие
ordered-target-chain — порядок важен, например Discord desktop updater → app/API → gateway → CDN/media
```

Для `discord-desktop` порядок target-ов теперь начинается с updater-фазы `stable.dl2.discordapp.net` / `updates.discord.com`, потому что owner verification упиралась в `Checking for updates`. GUI получил read-only `Policy` и `Tournament` actions, а CLI получил:

```bash
PYTHONPATH=gui python -m zap2_gui.app --blockcheck-service-policy --blockcheck-target-preset discord-desktop
PYTHONPATH=gui python -m zap2_gui.app --blockcheck-tournament --blockcheck-target-preset discord-desktop
```

Этот слой не запускает sudo и не доказывает одну `nfqws2`-команду на всех доменах автоматически; он фиксирует общий контракт для следующего шага и делает текущую диагностику updater-first.



## v0.4-alpha Stage 7b — phase-aware one-strategy tournament

Stage 7b уточняет модель Stage 7a по схеме владельца: стратегии проверяются по одной, а не пачкой `N` стратегий на одном домене. Одна стратегия-кандидат идёт через цепочку фаз и либо становится новым рекордсменом, либо попадает в непрошедшие.

Универсальный контракт теперь такой:

```text
any-target-available — достаточно любого рабочего target, как в простом YouTube baseline
maximize-targets — порядок не важен, но нужно максимизировать покрытие
ordered-target-chain — порядок важен; фазы идут через AND, targets внутри фазы идут через OR
```

Для Discord desktop non-voice цепочка фаз выглядит так:

```text
1. updater/bootstrap: stable.dl2.discordapp.net OR updates.discord.com
2. app-api: discord.com
3. gateway: gateway.discord.gg
4. cdn-media: cdn.discordapp.com OR media.discordapp.net OR discord.media OR discordapp.net
5. invite: discord.gg
```

Это исправляет ошибку Stage 7a: `updates.discord.com` больше не является абсолютным первым blocker-ом, если та же updater-фаза может быть пройдена через `stable.dl2.discordapp.net`.

Добавлен план one-strategy validation через upstream custom lists. Он записывает ровно одну `nfqws2`-стратегию в `.zap2/blockcheck/tournament/custom-lists/<strategy>/list_https_tls12.txt` и `list_https_tls13.txt`, чтобы следующий шаг мог проверять кандидата по фазам без предварительного накопления произвольной пачки стратегий на одном target-е.

CLI read-only пример:

```bash
PYTHONPATH=gui python -m zap2_gui.app --blockcheck-tournament --blockcheck-target-preset discord-desktop
PYTHONPATH=gui python -m zap2_gui.app --blockcheck-validate-strategy-plan <strategy-id> --blockcheck-domains discord.com
```

Граница Stage 7b: патч фиксирует фазовую модель, record-holder семантику и one-strategy custom-list bridge. Полный автоматический GUI-run, который сам берёт кандидата, гонит его по всем фазам и останавливается на полном покрытии, остаётся следующим реализационным слоем поверх этого контракта.

## v0.4-alpha Stage 7c — phase-gated tournament runner correction

Stage 7c corrects the Stage 7b runner mismatch observed during owner testing: the GUI must not continue to later Discord phases after an earlier required phase has no AVAILABLE alternative. The previous Stage 7b report described one-strategy tournament semantics, but the live `Scan all preset targets` runner still behaved like raw target coverage and could continue from blocked updater/app/gateway phases to a later CDN target.

The GUI Blockcheck runner is now phase-gated for presets with `ordered-target-chain` policy:

```text
phase 1 alternatives are tested first
if any alternative becomes AVAILABLE -> stop that candidate and advance to phase 2
if every alternative in the current required phase fails/dead-targets -> stop before later phases
later phases are never scanned out of order just because they appear later in the domain list
```

For Discord desktop non-voice this means:

```text
updater/bootstrap: stable.dl2.discordapp.net OR updates.discord.com
then app-api: discord.com
then gateway: gateway.discord.gg
then cdn-media alternatives
then invite
```

This patch intentionally preserves the Stage 7b one-strategy custom-list bridge. The full automatic record-holder validator is still a separate layer, but the GUI no longer produces misleading "random later domain" evidence when the ordered phase chain has already blocked.


## v0.4-alpha Stage 7d — Discord port-precheck и Blockcheck Lab UX

Stage 7d фиксирует два наблюдения owner-run после Stage 7c.

Первое: `stable.dl2.discordapp.net` уже давал десятки `AVAILABLE` стратегий, но следующий запуск мог пометить его `dead-target` на основании одного неудачного `nc` в port precheck. Для Discord ordered phases это слишком агрессивно: CDN/updater адреса могут быть плавающими, а `nc`-проверка не должна блокировать сам подбор стратегии. Поэтому Blockcheck Lab получил режим `dead-target guard`: для простых проверок он остаётся `auto-stop`, а для `discord-desktop` по умолчанию выставляется `observe-only`. В `observe-only` портовый precheck остаётся в логе и статистике, но GUI не убивает candidate до strategy scan.

Второе: экран Blockcheck Lab стал слишком плотным после добавления service policy/tournament controls. Stage 7d расширяет дефолтное окно, делит действия на две строки, укорачивает подписи кнопок и добавляет явный переключатель `Auto-skip dead target`, чтобы владелец видел, когда включён риск раннего пропуска candidate.

Граница Stage 7d: патч не портирует Flowseal/Windows presets в исполняемый Linux runtime автоматически. Он фиксирует источник ложного `dead-target`, улучшает управляемость GUI и документирует, какие идеи Flowseal/Windows стоит переносить осторожно.

## v0.4-alpha Stage 7f — bounded phase alternatives and core notes

Stage 7f fixes the owner-observed case where the phase-gated runner stayed on the first updater alternative (`stable.dl2.discordapp.net`) until manual Stop. The runner still follows the owner model — phases are `AND`, alternatives inside a phase are `OR`, and later phases are not checked until the current required phase is satisfied — but each phase alternative now has an owner-visible `Alt check cap`.

For `discord-desktop` the default cap is 160 strategy checks per alternative. If an `AVAILABLE` strategy appears first, the GUI stops that upstream candidate and advances to the next phase. If the cap is reached with no `AVAILABLE`, the GUI stops only that candidate and tries the next alternative in the same phase. Setting the cap to `off` restores the previous unbounded behavior for deep single-target scans.

Stage 7f also records core reference notes from `core/zapret2`: upstream custom blockcheck lists can be supplied via `LIST_HTTP`, `LIST_HTTPS_TLS12`, `LIST_HTTPS_TLS13` and `LIST_QUIC`, and `nfqws2` profile ordering is first-match-wins. These notes are captured in `docs/ZAPRET2_CORE_BLOCKCHECK_NOTES.md` for the future real one-strategy validator and possible multi-profile Discord runtime work.

The Blockcheck Lab layout is widened again and key controls now have maximum widths plus a reserved two-line preset description area, so the diagnostics screen is less edge-stretched and less vertically overlapped.
