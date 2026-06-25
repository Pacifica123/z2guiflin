# v0.4-alpha Stage 1: roadmap выбора YouTube или Discord

`v0.4-alpha_stage_1` фиксирует план реализации цели `v0.4-*` по патчам. Это
документационный stage: он не меняет runtime, не добавляет новые firewall rules и
не обещает одновременную работу YouTube и Discord.

Главная цель цикла остаётся простой: в конце `v0.4-*` пользователь должен иметь
понятный выбор целевого сервиса и запустить рабочую цепочку хотя бы для одного
выбранного сервиса:

```text
выбрать YouTube -> прогнать/выбрать YouTube strategy -> запустить Default workflow
или
выбрать Discord -> прогнать/выбрать Discord strategy -> запустить Default workflow
```

Одновременная работа YouTube и Discord допускается как удачный побочный эффект,
но не является критерием готовности `v0.4-*`. Автоматическая композиция
нескольких сервисов в одну универсальную стратегию переносится на будущую веху.

## Почему первый шаг действительно небольшой

Для non-voice части desktop Discord текущая гипотеза такая: уже существующая
цепочка YouTube может быть повторена на Discord-доменах. То есть первый
реализационный шаг после этого документа должен быть не переписыванием runtime,
а service preset для Blockcheck и hostlist/runtime target alignment.

Базовый Discord target seed для первого non-voice прохода:

```text
discord.com
gateway.discord.gg
cdn.discordapp.com
discordapp.net
discord.media
media.discordapp.net
updates.discord.com
discord.gg
```

Ожидаемый результат первого Discord-прохода: desktop-клиент запускается,
подключается к gateway, показывает чаты и грузит базовые media/CDN ресурсы.
Голосовые каналы не входят в этот минимальный критерий.

## Термины цикла

### Service target preset

Именованный набор доменов/probes, который Blockcheck lab может подставить без
ручного ввода длинной строки. Минимальные presets цикла:

- `youtube-basic` — сохраняет уже подтверждённую YouTube-цепочку;
- `discord-desktop` — добавляет Discord desktop non-voice targets;
- `custom` — оставляет владельцу ручной ввод доменов.

### Active service target

Выбранный пользователем сервисный фокус текущего прогона. В `v0.4-*` он нужен не
для запрета второго сервиса, а для снижения неоднозначности: GUI должен явно
показывать, что сейчас пользователь подбирает или запускает стратегию под
YouTube, Discord или custom target.

### Service-aware generated strategy

Generated strategy должна сохранять достаточно metadata, чтобы пользователь видел
не только строку `nfqws2`, но и исходный сервисный контекст: preset, source target,
protocol family и путь к successful blockcheck log. Это не меняет смысл стратегии,
но предотвращает путаницу между YouTube и Discord результатами.

## План патчей v0.4-alpha

### Stage 1 — roadmap и критерии готовности

Текущий patch. Фиксирует:

- цель финального `v0.4-*` как выбор между YouTube и Discord;
- отсутствие обязательной гарантии одновременной работы;
- Discord non-voice как первый реализационный слой;
- voice/UDP как отдельную позднюю задачу;
- последовательность следующих патчей.

### Stage 2 — registry service target presets

Реализационный patch добавляет кодовый registry presets без изменения runtime apply:

- `youtube-basic` с текущими `youtube.com www.youtube.com`;
- `discord-desktop` с Discord target seed;
- `custom` как безопасный ручной режим;
- shared validation для доменов/URI без shell-like targets;
- unit tests на состав доменов, имена presets, default YouTube baseline и запрет опасных tokens.

Ожидаемый результат: в коде появляется единый источник правды для target lists,
но GUI ещё остаётся минимальным. Selector и CLI-флаг preset — задача Stage 3.

### Stage 3 — Blockcheck Lab preset selector

Текущий patch подключает Stage 2 registry к GUI и CLI:

- combobox `Service target` в Blockcheck Lab;
- автозаполнение доменного поля при выборе YouTube/Discord;
- preset-owned targets отображаются read-only, а ручные правки делаются через `custom`;
- CLI-флаг `--blockcheck-target-preset discord-desktop`;
- `--blockcheck-domains` остаётся ручным custom override;
- тесты подтверждают, что default поведение не ломает YouTube baseline.

Ожидаемый результат: Discord можно прогнать без ручного вписывания всех доменов.
Stage 3 всё ещё не меняет runtime apply и hostlist.

### Stage 4 — Discord hostlist/runtime alignment

Текущий patch синхронизирует то, что проверяется Blockcheck, с тем, к чему затем
применяется Default workflow:

- добавлены недостающие Discord hostlist entries, особенно `gateway.discord.gg`,
  `cdn.discordapp.com`, `media.discordapp.net`;
- default hostlist теперь покрывает полный `discord-desktop` non-voice seed из
  registry;
- YouTube entries не удалены и остаются baseline-путём;
- добавлен parser/validator, который проверяет drift между service target preset
  и hostlist;
- автоматическое объединение несовместимых `nfqws2` args не вводится.

Ожидаемый результат: если Blockcheck нашёл стратегию для Discord target, runtime
не теряет этот target на стадии применения через Default workflow hostlist.

### Stage 5 — service-aware export и Strategy UX

Текущий patch уменьшает риск выбора «не той» стратегии:

- `BlockcheckOptions` сохраняет `service_target_preset_id`;
- Blockcheck plan/log пишет `service target preset: ...` и
  `ZAP2_SERVICE_TARGET_PRESET=...`;
- exporter использует этот service id при генерации strategy id/title/metadata;
- generated JSON получает блок `serviceTarget`;
- вкладка `Стратегии` и CLI-детали показывают сервисный контекст;
- active strategy для Default profile остаётся одной выбранной стратегией;
- пользователь явно понимает, что переключение с YouTube strategy на Discord
  strategy меняет текущий фокус запуска.

Ожидаемый результат Stage 5: Discord-generated и YouTube-generated strategies
различимы без ручного открытия каждого JSON, но runtime всё ещё запускает только
одну явно выбранную strategy.

### Stage 6 — owner verification loop для Discord non-voice

Текущий patch добавляет owner-facing проверочный сценарий:

- CLI `--discord-verification-plan` показывает полную петлю проверки без исполнения;
- CLI `--discord-verification-template` создаёт `.zap2/verification/discord-non-voice-owner-check.md`;
- вкладка Blockcheck lab получает кнопку `Discord checklist`;
- сценарий ведёт владельца через Discord preset, export `AVAILABLE`, выбор generated Discord strategy и Default workflow;
- success checklist разделяет login/session, gateway, список серверов, чаты и CDN/media;
- failure buckets разделяют no-available, dead target, wrong strategy selection, gateway-only failure и CDN/media failure;
- voice/UDP, звонки и screen share явно исключены из критерия успеха.

Ожидаемый результат: владелец получает evidence log, по которому Stage 7 сможет
понять, достаточно ли доменного подхода для desktop Discord non-voice и какие
точечные исправления действительно нужны.

### Stage 7 — точечные исправления по результатам Discord проверки

Этот stage резервируется под реальные наблюдения владельца:

- dead targets;
- лишние или отсутствующие домены;
- конфликтующие protocols;
- неправильные имена generated strategies;
- regression в YouTube baseline.

Ожидаемый результат: Discord non-voice становится достаточно воспроизводимым для
перехода к beta-кандидату или к voice-исследованию.

### Stage 8 — optional Discord voice/UDP investigation

Не начинать до подтверждения non-voice слоя. Voice требует отдельного подхода:

- UDP queue scope;
- `--filter-udp`, а не только `--filter-l7=stun,discord`;
- STUN/Discord IP discovery payloads;
- отдельные риски широких UDP-диапазонов.

Ожидаемый результат: либо voice явно выносится за рамки `v0.4-*`, либо получает
собственный owner-approved plan без смешивания с non-voice baseline.

## Критерии готовности финального v0.4-* patch

Финальный patch цикла можно считать достигшим цели, если выполнены условия:

- YouTube baseline не утрачен: его можно выбрать как отдельный service target;
- Discord desktop non-voice можно выбрать как отдельный service target;
- Blockcheck lab не требует ручного запоминания всех Discord-доменов;
- generated strategies имеют понятный service context;
- Default workflow запускает выбранную стратегию через прежний confirmation/sudo
  safety boundary;
- владелец может выбрать YouTube или Discord и получить рабочий результат хотя
  бы для одного выбранного сервиса в своём окружении;
- документация честно говорит, что одновременная работа двух сервисов не
  гарантируется в `v0.4-*`.

## Что не делать внутри v0.4-alpha без отдельного решения

- Не вводить скрытый режим «лечить всё сразу».
- Не удалять подтверждённый YouTube путь ради Discord.
- Не считать Discord voice частью минимального non-voice успеха.
- Не запускать privileged changes без существующего owner-confirmed workflow.
- Не импортировать Windows GUI presets целиком: брать из них target knowledge, но
  не переносить Windows-specific WinDivert/wf-фрагменты в Linux runtime.
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


### v0.4-alpha Stage 7n1 — active pre-TLS state probe

Adds active nft/NFQUEUE state reporting for Discord pre-TLS diagnostics: running/applied strategy, session PID health, corrected nft counter commands, and a read-only `--runtime-pretls-probe` checklist.


## Stage 7n2 — guided Discord pre-TLS probe harness

Stage 7n2 turns the Stage 7n/7n1 observability pieces into one guided owner-facing run. It writes JSON/Markdown reports with nft counter deltas, nfqws2 health, qnum consistency, log/debug deltas, a verdict, and the next allowed branch. It intentionally does not add another Discord bypass strategy.

## v0.4-alpha Stage 7p0 — Discord SOCKS/VLESS tunnel technical plan

Stage 7p0 opens a second Discord recovery lane next to the existing zapret direct
strategy work.  The new lane is not another desync preset: it is a plan for a
Discord SOCKS/VLESS tunnel backend that can route Discord through a local proxy
managed by Zap2GUIfLin.

The planned split is:

```text
zapret direct strategy  -> keep Discord direct and alter/capture early packets
Discord tunnel lane     -> use an external core and local SOCKS proxy
```

Stage 7p0 is documentation-only.  It records how connection strings will be
imported, how secrets will be redacted, how v2rayNG can be used as a conceptual
reference, why Zap2 should orchestrate an external core instead of implementing
VLESS itself, and why update-only mode must be treated as a single proxied launch
window rather than a proxy-then-restart trick.

Safety boundary:

```text
no automatic external downloads
no copied third-party Android/Kotlin implementation
no committed owner connection string
no firewall/service changes
no Discord launch
```

The next implementation layer should be Stage 7p1: a pure VLESS URI parser and
`.zap2/tunnel` connection-profile model with redaction tests.


## v0.4-alpha Stage 7p1-7p4 — Experimental Discord SOCKS/VLESS tunnel MVP

Stage 7p1-7p4 turns the Stage 7p0 plan into the first CLI/runtime MVP for the
new tunnel lane.  It adds VLESS URI import, redacted connection selection,
external core config generation, owner-confirmed start/stop for an installed
core, loopback SOCKS probing, and a Discord launch wrapper using proxy
environment variables plus Chromium/Electron `--proxy-server` candidates.

This lane is deliberately separate from the zapret/NFQUEUE lane.  It does not
download cores, does not commit owner connection strings, does not modify
firewall/service state, and refuses to run while the default zapret workflow is
already active.  The next planned layer is Stage 7p5: a guided updater-window
experiment that records whether Discord actually uses the local SOCKS listener
and whether the updater passes.

## v0.4-alpha Stage 7p5 — Guided Discord SOCKS/VLESS tunnel experiment

Stage 7p5 continues the Stage 7p1-7p4 tunnel MVP with a stronger guided workflow:

- harmless HTTPS-over-SOCKS probe for `updates.discord.com` or a custom target;
- one-command owner-user-space guided run that prepares, confirms, starts,
  probes, launches Discord, and writes a report;
- additional launch modes for comparing env-only versus Chromium flag-only proxy
  behavior;
- a lightweight `Туннель` GUI tab for read-only status/probe actions;
- plan-only TUN/TProxy research command, deliberately not a privileged executor.

This stage still avoids copying v2rayNG code.  v2rayNG remains a reference for
product patterns: profile list, proxy-only mode, VPN/TUN separation, and test
service concepts.


### Stage 7x — HAR discovery/reporting cleanup

Этот patch закрывает две технические задачи перед дальнейшими Discord-итерациями.
Первая — инвентаризация core больше не падает из-за `lua/custom_funcs.lua`: общий
core count и upstream import count разделены явно. Вторая — browser HAR теперь
можно использовать безопасно: анализатор строит sanitized host/path/status
summary, показывает категории и coverage gaps, но не сохраняет секретные headers,
cookies, query strings, bodies, WebSocket payloads или server IP values.

Ожидаемый результат: следующий stage получает более чистый evidence слой. HAR
помогает понять web-surface Discord, но не подменяет Blockcheck, endpoint watch и
pre-TLS probe для текущего ClientHello/no-ServerHello blocker.


## v0.4-alpha Stage 7y — GUI VLESS clipboard import

Stage 7y makes the existing SOCKS/VLESS tunnel lane usable from the GUI instead
of forcing every connection-profile import through the terminal. The `Туннель`
tab now has a dedicated `VLESS import` block:

```text
Import from clipboard  -> one-click import of copied vless:// text
Preview field          -> parse/redact without writing files
Import from field      -> manual paste fallback
Import from file       -> local text/subscription file fallback
Profiles and probes    -> separate status/probe action block
```

The adapter also accepts base64 subscription text and multiple VLESS links in one
payload. Import still does not start the external core, does not launch Discord,
does not use sudo, and does not mutate firewall/systemd state. Raw VLESS URI
values stay out of GUI output and repository files; runtime profile storage
remains under `.zap2/tunnel` with secret file permissions where possible.

The v2rayNG reference was used only for the product pattern: direct clipboard
import plus batch/base64 parsing. No Android/Kotlin implementation code is copied.

## v0.4-alpha Stage 7z — GUI launch composer

Stage 7z adds the first composition layer above separate Zapret and tunnel lanes. The goal is a GUI panel where the owner can choose an experiment set instead of hunting for isolated buttons.

Implemented components:

- `zapret-default`: current default workflow, still owner-confirmed and privileged through GUI sudo-askpass;
- `tunnel-vless`: current VLESS external-core lane, still user-space and managed by `.zap2/tunnel` PID state.

Reserved placeholders:

- `socks5`;
- `mtproto`;
- `custom`.

The composer exposes status, plan, start, and stop actions. Status/plan are read-only. Start refuses planned components, prepares and confirms the required child plans, and then runs supported components in a stable order. Stop reverses that order.

Combination policy changed only for explicit composer experiments: tunnel start can allow a running Zapret workflow when the composer selected both components. The direct tunnel lane remains conservative by default.
