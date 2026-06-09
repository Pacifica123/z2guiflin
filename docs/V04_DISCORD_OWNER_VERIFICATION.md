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

Для `discord-desktop` порядок target-ов теперь начинается с `updates.discord.com` и `stable.dl2.discordapp.net`, потому что owner verification упиралась в `Checking for updates`. GUI получил read-only `Policy` и `Tournament` actions, а CLI получил:

```bash
PYTHONPATH=gui python -m zap2_gui.app --blockcheck-service-policy --blockcheck-target-preset discord-desktop
PYTHONPATH=gui python -m zap2_gui.app --blockcheck-tournament --blockcheck-target-preset discord-desktop
```

Этот слой не запускает sudo и не доказывает одну `nfqws2`-команду на всех доменах автоматически; он фиксирует общий контракт для следующего шага и делает текущую диагностику updater-first.

