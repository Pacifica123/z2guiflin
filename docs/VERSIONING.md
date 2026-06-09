# Политика версионирования

## Текущая метка продукта

```text
v0.4-alpha
```

`v0.4-alpha` открывает новый цикл после owner-declared `v0.3-stable`. Предыдущая stable-точка доказала end-to-end цепочку для YouTube: Blockcheck lab нашёл `AVAILABLE` стратегии, GUI экспортировал их в `strategies/generated/`, пользователь выбрал strategy во вкладке `Стратегии`, затем Default workflow запустил `nfqws2` и это реально сработало в целевом окружении.

## Форма

Метки продукта используют формат:

```text
v<major>.<minor>-<phase>[-hf_<shortFixName>]
```

Фазы:

- `alpha` открывает цикл и может охватывать много devctl-патчей;
- `beta` означает, что цель цикла реализована достаточно для концентрированной проверки;
- `dev` означает, что владелец использует продукт для более длительного real-world testing;
- `stable` может объявить только владелец.

## Stage id для v0.3-alpha

Новый поток сбрасывает нумерацию стадий внутри продуктовой метки:

```text
v0.3-alpha_stage_1
v0.3-alpha_stage_2
v0.3-alpha_stage_3
```

Не продолжать историческую нумерацию Stage 50+. Исторические ссылки остаются валидны как old-line notes, но не как активная последовательность.

## Правила продвижения

- Ассистент не должен самостоятельно продвигать проект до `stable`.
- Не переименовывать каждый патч в новую product version.
- Использовать devctl patch id для идентичности патча и product label для идентичности вехи.
- Hotfix suffixes предназначены для `beta` и `dev`, а не для обычного `alpha` patch flow.

## Язык документации

Версионирование не меняет правило языка: вся активная проектная документация будущих патчей пишется на русском, даже если patch id, имена файлов и технические идентификаторы остаются англоязычными.

## Переход Stage 14 к v0.3-beta

После `v0.3-alpha_stage_14` продуктовая метка становится `v0.3-beta`, потому что alpha-цепочка controlled runtime lifecycle закрыта: есть профили/стратегии, runtime contracts, plan generator, state/log/confirmation gate, session runner, owner-confirmed apply/revert, service plans и default start/stop workflow.

Дальнейшие патчи должны именоваться от `v0.3-beta`, если они не являются срочными hotfix-патчами к уже выпущенному Stage 14.

## Переход v0.3-beta → v0.3-dev

`v0.3-beta` зафиксировала контролируемую runtime baseline: build, plan,
confirmation, apply/revert, session и GUI toggle. `v0.3-dev` — следующий
разработческий цикл поверх этой базы. Его первая цель — не расширять поверхность,
а стабилизировать запуск: корректный devctl patch format, чистое дерево
инструментов и более безопасный NFQUEUE scope.

## Сброс нумерации внутри v0.3-dev

Переходные патчи, которые перевели ветку к `v0.3-dev` и исправили старт после
safer interception, исторически назывались Stage 16/17, потому что продолжали
предыдущую beta-цепочку. Начиная с GUI Blockcheck lab, dev-цикл нумеруется
заново:

```text
v0.3-dev_stage_1
v0.3-dev_stage_2
v0.3-dev_stage_3
v0.3-dev_stage_4
v0.3-dev_stage_5
```

Это не меняет продуктовую метку `v0.3-dev`, но делает следующие dev-патчи
читабельными и отделяет новый цикл от закрытого alpha/beta runtime baseline.

## v0.3-dev Stage 2

`v0.3-dev_stage_2` продолжает новый dev-цикл после Blockcheck lab и добавляет
локальную сборку prerequisites для него: `nfqws2` и `mdig` больше не должны
обнаруживаться только после запуска privileged upstream script. Номер Stage 2
подтверждает сброшенную dev-нумерацию и не возвращается к историческим Stage
16/17.

## v0.3-dev Stage 4

`v0.3-dev_stage_4` продолжает Blockcheck lab и исправляет запуск upstream
`blockcheck2.sh` в пользовательском workspace: GUI wrapper теперь передаёт
`WS_UID/WS_GID` владельца, чтобы `nfqws2` после privilege drop мог читать
`core/zapret2/lua/*.lua`. Номер Stage 4 остаётся внутри сброшенного dev-цикла.


## v0.3-dev Stage 5

`v0.3-dev_stage_5` продолжает Blockcheck lab без изменения продуктовой метки.
Stage 5 не добавляет автоматических эвристик ранней остановки и не меняет
privileged boundary; он только сохраняет краткую статистику по уже увиденному
выводу blockcheck после Stop или finish. Это помогает анализировать длинные
прогоны, где большинство candidate strategies завершается одинаковой ошибкой,
например `curl code 28: connection timed out`.

## v0.3-dev Stage 6

`v0.3-dev_stage_6` продолжает Blockcheck lab и замыкает первую полноценную
пользовательскую петлю подбора стратегии: available results из blockcheck можно
экспортировать в `strategies/generated/`, увидеть во вкладке `Стратегии`, выбрать
одну из них для Default profile и затем заново пройти обычный plan/confirmation
путь запуска. Номер Stage 6 остаётся внутри сброшенного dev-цикла.

## v0.3-dev Stage 7

`v0.3-dev_stage_7` продолжает Blockcheck lab без изменения продуктовой метки. Основной смысл stage — evidence-based управление долгими blockcheck-запусками: sequential candidates, автоматический skip target с мёртвым TCP/443 port precheck и экспорт только из последнего successful blockcheck source.

## Переход v0.3-dev → v0.3-stable

После `v0.3-dev_stage_7` владелец проекта забэкапировал состояние как `v0.3-stable`. Это решение принимает владелец, а не ассистент. Смысл stable-точки:

- Blockcheck lab умеет реально прогонять upstream `blockcheck2.sh` без заморозки GUI;
- prerequisites для `nfqws2`/`mdig` собираются локально и явно;
- долгие прогоны имеют live log, Stop и краткую статистику;
- sequential candidates не тратят scan на target с мёртвым TCP/443 precheck;
- найденные `AVAILABLE` стратегии экспортируются в `strategies/generated/`;
- стратегия выбирается во вкладке `Стратегии`;
- Default workflow строится по выбранной strategy id и запускается через owner-confirmed sudo-askpass путь;
- в целевом окружении владельца это уже сработало как минимум для YouTube.

## Переход v0.3-stable → v0.4-alpha

`v0.4-alpha` начинается не с переписывания runtime, а с расширения доказанной цепочки на новый сервис: desktop Discord. Цель цикла — подобрать рабочий набор target domains/probes для desktop Discord, получить generated strategy, выбрать её и проверить запуск через существующий Default workflow.

В рамках `v0.4-*` сознательно не решается задача автоматической композиции нескольких сервисов в одну универсальную стратегию. Допустимый UX для этого цикла:

```text
выбрать стратегию YouTube
или
выбрать стратегию Discord
```

но не обязательно:

```text
автоматически совместить YouTube + Discord без конфликтов
```

## Сброс нумерации внутри v0.4-alpha

Переход на `v0.4-alpha` снова сбрасывает stage-нумерацию. Этот документационный baseline считается `v0.4-alpha_stage_0`, чтобы зафиксировать новую цель и не смешивать её с закрытым `v0.3-dev` loop. Следующие реализационные патчи должны начинаться с:

```text
v0.4-alpha_stage_1
v0.4-alpha_stage_2
v0.4-alpha_stage_3
```

Stage id должен описывать конкретный шаг Discord desktop cycle, например candidate discovery, Discord Blockcheck preset, strategy export UX или runtime verification.

## v0.4-alpha Stage 1

`v0.4-alpha_stage_1` остаётся внутри product label `v0.4-alpha` и является
документационным roadmap patch. Он не продвигает проект к `beta` и не меняет
runtime-поведение.

Stage 1 фиксирует, что финальная цель `v0.4-*` — выбор между рабочим YouTube
путём и рабочим Discord desktop путём. В рамках этой вехи не требуется
гарантировать их одновременную работу одной универсальной стратегией. Следующие
реализационные stages должны двигаться от простого service target preset к
hostlist/runtime alignment, service-aware export и owner verification loop.

## v0.4-alpha Stage 2

`v0.4-alpha_stage_2` является первым реализационным патчем после roadmap. Он
добавляет registry service target presets: `youtube-basic`, `discord-desktop` и
`custom`. Default Blockcheck по-прежнему использует YouTube baseline, поэтому
рабочая `v0.3-stable` цепочка не должна измениться.

Stage 2 намеренно не добавляет GUI selector, CLI-флаг preset, hostlist alignment
или runtime switching. Эти шаги остаются следующими стадиями `v0.4-alpha`.

## v0.4-alpha Stage 3

`v0.4-alpha_stage_3` остаётся внутри product label `v0.4-alpha`. Он подключает
service target registry к Blockcheck Lab и CLI: пользователь может выбрать
`youtube-basic`, `discord-desktop` или `custom` без копирования длинных доменных
строк вручную.

Stage 3 не продвигает проект к `beta`, потому что Discord hostlist/runtime
alignment и service-aware export ещё не завершены. Следующие патчи должны
продолжать текущую stage-нумерацию и не менять правило: YouTube baseline не
удаляется ради Discord.

## v0.4-alpha Stage 4

`v0.4-alpha_stage_4` закрывает hostlist/runtime alignment для первого Discord
non-voice прохода. Он добавляет в default hostlist недостающие Discord entries
`gateway.discord.gg`, `cdn.discordapp.com` и `media.discordapp.net`, а также
фиксирует тестовый contract: `youtube-basic` и `discord-desktop` preset-ы должны
быть покрыты `profiles/hostlists/default.hosts`.

Stage 4 не вводит service auto-switching, не переносит Windows presets целиком и
не обещает одновременную работу YouTube и Discord. Это только выравнивание
Blockcheck targets и runtime hostlist перед следующей стадией service-aware
export/Strategy UX.

## v0.4-alpha Stage 5

`v0.4-alpha_stage_5` закрывает service-aware export и первый слой Strategy UX.
Blockcheck plan/log теперь сохраняет `service_target_preset_id`, exporter
создаёт generated strategy id/title/metadata с привязкой к `youtube-basic`,
`discord-desktop` или `custom`, а вкладка `Стратегии` и CLI-детали показывают
service target label.

Stage 5 не переводит проект в `beta`: ещё нет owner verification loop, где
владелец выбирает generated Discord strategy, запускает Default workflow и
проверяет desktop Discord non-voice в реальной среде. Одновременно Stage 5 не
ломает YouTube baseline и не вводит автоматическое объединение YouTube/Discord
стратегий.

## v0.4-alpha Stage 6: owner verification loop для Discord non-voice

`v0.4-alpha_stage_6` добавляет последний слой перед личной проверкой владельца:
read-only verification loop и markdown-шаблон отчёта. Новый CLI:

```bash
PYTHONPATH=gui python -m zap2_gui.app --discord-verification-plan
PYTHONPATH=gui python -m zap2_gui.app --discord-verification-template
```

План описывает GUI/CLI-петлю: прогнать `discord-desktop`, экспортировать
`AVAILABLE` стратегии, выбрать generated Discord strategy, запустить Default
workflow обычным owner-confirmed путём, полностью перезапустить desktop Discord и
отметить non-voice признаки: login/session, gateway, список серверов, чаты,
CDN/media. Шаблон создаётся в `.zap2/verification/discord-non-voice-owner-check.md`
и не перезаписывает уже заполненные заметки.

Stage 6 не запускает проверки автоматически, не меняет firewall/services и не
считает voice/UDP частью успеха. Его задача — собрать evidence для Stage 7: что
именно сломалось или подтвердилось в окружении владельца.
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

## v0.4-alpha Stage 7g note

Stage 7g is a diagnostic pivot inside the Discord desktop investigation. It does not claim a working Discord strategy. It adds read-only endpoint discovery and another Blockcheck Lab UI cleanup so the next patch can be based on observed local updater sockets instead of guessed updater domains.

## Stage 7h: updater socket state discovery

Stage 7h extends the Stage 7g endpoint discovery loop with TCP state/timer evidence and best-effort DNS mapping. The owner observed the Discord updater splash opening a TCP/443 socket in `SYN-SENT` toward a Cloudflare edge IP that resolves in the current environment for `updates.discord.com`. This means the failure is visible before a completed TLS/HTTP request on that socket, so more curl/TLS strategy tournaments against later Discord phases are not the next best diagnostic step.

New CLI helpers:

```bash
PYTHONPATH=gui python -m zap2_gui.app --discord-endpoint-watch --discord-endpoint-seconds 30
PYTHONPATH=gui python -m zap2_gui.app --discord-endpoint-report
PYTHONPATH=gui python -m zap2_gui.app --discord-netlog-plan
```

The watcher remains read-only: it samples `ss`, `pgrep` and DNS metadata, does not use sudo, does not mutate firewall/services and does not capture packet payloads. The optional netlog plan is not executed automatically because Chromium netlogs can contain privacy-sensitive URLs, headers or token-like values.

### v0.4-alpha Stage 7i — Discord DNS edge diagnosis

Stage 7i переносит идею Windows GUI DNS-проверок в read-only Linux diagnostic. Команды `--discord-dns-edge-plan` и `--discord-dns-edge-check` сравнивают system/Cloudflare/Google/Quad9/AdGuard/OpenDNS resolvers и проверяют TCP/443 для возвращённых Discord edge IP. Это не меняет DNS и не требует sudo. Если найден `connect-ok` edge, DNS/hosts steering можно рассматривать как owner-confirmed эксперимент. Если все edge IP timeout, то текущий Discord updater blocker шире, чем DNS-подмена, и обычные TLS Blockcheck-стратегии всё ещё не упражняются на SYN-SENT socket.
