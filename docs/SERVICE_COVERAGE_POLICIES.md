# Service coverage policies

Stage 7a вводит общий слой `service coverage policy`: это не список доменов и не конкретная `nfqws2`-стратегия, а контракт между владельцем, GUI и Blockcheck adapter о том, как понимать результат проверки service target preset.

## Зачем это нужно

YouTube baseline и desktop Discord требуют разных критериев успеха.

Для простого доменного сценария достаточно ответа:

```text
нашлась хотя бы одна AVAILABLE strategy на одном полезном target
```

Для desktop-приложения этого мало. Если приложение стартует через updater, затем открывает app/API, затем держит gateway/WebSocket и отдельно грузит CDN/media, полезный результат должен показывать не только «есть AVAILABLE», а ещё:

```text
какой слой прошёл
какой слой первый сломался
насколько близко мы подошли к полной service coverage
```

## Режимы

### `any-target-available`

Простой режим. Порядок target-ов не важен, первый рабочий target уже является полезным кандидатом.

Используется для:

```text
youtube-basic
```

Recommended scan mode:

```text
stop-after-first-available
```

### `maximize-targets`

Порядок target-ов не важен, но важно покрыть как можно больше target-ов. Этот режим оставлен как универсальный задел для будущих desktop/service presets, у которых нет строгого bootstrap-порядка, но один домен не является достаточным доказательством.

### `ordered-target-chain`

Порядок target-ов важен. Проверка читается как цепочка: если ранний слой не проходит, поздние успехи не доказывают запуск приложения.

Используется для:

```text
discord-desktop
```

Recommended scan mode:

```text
scan-all-targets
```

Discord desktop non-voice order в Stage 7a:

```text
1. stable.dl2.discordapp.net
2. updates.discord.com
3. discord.com
4. gateway.discord.gg
5. cdn.discordapp.com
6. media.discordapp.net
7. discord.media
8. discordapp.net
9. discord.gg
```

Updater/download targets идут первыми, потому что owner verification показала зависание desktop Discord на `Checking for updates` до app shell.

## Tournament snapshot

Stage 7a добавляет read-only tournament snapshot. Он читает текущий coverage manifest и считает:

```text
score: сколько target-ов уже available
ordered prefix: сколько target-ов подряд прошло с начала цепочки
first blocker: первый target, который не available
full coverage: закрыта ли вся цепочка
```

Команда:

```bash
PYTHONPATH=gui python -m zap2_gui.app --blockcheck-tournament --blockcheck-target-preset discord-desktop
```

GUI:

```text
Blockcheck lab → Tournament
```

## Граница Stage 7a

Stage 7a не утверждает, что upstream `blockcheck2.sh` уже умеет взять одну найденную `nfqws2`-команду и автоматически доказать её на каждом следующем target-е. Это следующий возможный шаг поверх введённого policy/tournament контракта.

Текущая польза Stage 7a:

```text
- все preset-ы получили явную coverage policy;
- Discord scan начинает с updater/download targets;
- GUI/CLI показывают policy одинаковыми словами;
- coverage manifest сохраняет policy metadata;
- Strategy export получает coveragePolicy snapshot;
- owner stop всё равно оставляет best-so-far target evidence для Tournament view.
```

## Safety boundary

Policy и tournament view являются read-only слоями. Они не запускают sudo, не меняют firewall/services и не выбирают стратегию автоматически.


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

