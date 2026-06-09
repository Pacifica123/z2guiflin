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
