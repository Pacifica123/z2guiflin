# v0.4-alpha Stage 6: Discord non-voice owner verification loop

Stage 6 — последний подготовительный слой перед личной проверкой владельца. Он
не пытается сам доказать, что Discord работает в конкретной сети: такую проверку
может выполнить только владелец на своей машине. Задача stage — дать
повторяемую петлю действий и шаблон отчёта, чтобы следующий Stage 7 опирался не
на догадки, а на evidence log.

## Граница проверки

Проверяется только desktop Discord non-voice:

- запуск приложения после полного закрытия и повторного старта;
- login или переподключение существующей сессии;
- gateway-соединение, список серверов и каналов;
- чтение и отправка текстовых сообщений;
- базовые CDN/media ресурсы: аватарки, иконки, изображения, attachments;
- отсутствие блокировки запуска из-за update/asset endpoints.

Не проверяется и не считается провалом Stage 6:

- voice channels;
- звонки;
- screen share;
- UDP/STUN discovery;
- гарантированная одновременная работа YouTube и Discord одной стратегией;
- автоматическое объединение нескольких generated strategies.

## CLI-петля

Сначала можно вывести план без исполнения:

```bash
PYTHONPATH=gui python -m zap2_gui.app --discord-verification-plan
```

Затем обычная ручная цепочка Discord non-voice:

```bash
PYTHONPATH=gui python -m zap2_gui.app --blockcheck-plan --blockcheck-target-preset discord-desktop
PYTHONPATH=gui python -m zap2_gui.app --blockcheck-run --blockcheck-target-preset discord-desktop
PYTHONPATH=gui python -m zap2_gui.app --blockcheck-export-strategies
PYTHONPATH=gui python -m zap2_gui.app --list-strategies
PYTHONPATH=gui python -m zap2_gui.app --select-strategy <blockcheck-discord-desktop-...>
PYTHONPATH=gui python -m zap2_gui.app --default-start-plan
PYTHONPATH=gui python -m zap2_gui.app --runtime-confirm runtime-default-<strategy>-default-start-workflow-plan
sudo PYTHONPATH=gui python -m zap2_gui.app --default-start --confirm runtime-default-<strategy>-default-start-workflow-plan
```

После запуска Default workflow владелец полностью закрывает desktop Discord,
запускает его заново и фиксирует наблюдения. Если проверка делается через GUI,
та же логика доступна во вкладке Blockcheck lab кнопкой `Discord checklist`.
Кнопка только показывает петлю проверки, не запускает сетевые действия и не
меняет firewall.

## Шаблон отчёта

Для записи результата Stage 6 добавляет локальный markdown-шаблон:

```bash
PYTHONPATH=gui python -m zap2_gui.app --discord-verification-template
```

Файл создаётся здесь:

```text
.zap2/verification/discord-non-voice-owner-check.md
```

Команда не перезаписывает существующий файл, чтобы не стереть ручные заметки
владельца. Шаблон содержит success checklist, failure buckets и отдельную пометку
`Voice/UDP: excluded from this report`.

## Что передать в Stage 7

Для точечного исправления в Stage 7 желательно сохранить:

- какой generated strategy id был выбран;
- какие Discord targets дали `AVAILABLE`;
- какие targets были dead/no-available;
- сработал ли gateway;
- грузились ли CDN/media;
- не было ли регрессии выбора YouTube baseline;
- вывод `--default-status` после запуска;
- краткое описание поведения desktop Discord после полного перезапуска.

Stage 7 не должен начинать voice/UDP-исследование, пока non-voice слой не
получит ясный результат. Если non-voice не подтверждён, сначала чинятся target
list, export/selection UX или runtime alignment. Если non-voice подтверждён,
voice остаётся отдельным optional исследованием с собственными UDP-границами.
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
