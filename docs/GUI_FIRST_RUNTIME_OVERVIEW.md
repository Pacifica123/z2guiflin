# GUI-first обзор runtime

Дата: 2026-06-29

Цель patch: перенести базовый Default workflow обратно в GUI-сценарий. Пользователь не должен вручную сопоставлять `plan id`, `pgrep`, `nft`, `grep` и guided-probe verdict, чтобы понять, что происходит.

## Что добавлено

Новый read-only adapter:

```text
gui/zap2_gui/adapters/gui_first_overview.py
```

Он собирает в один state:

```text
selected strategy
prepared start plan
running workflow strategy
nfqws2 session state
owner-rules / NFQUEUE state
overall state
primary GUI action
next GUI action
```

Состояния:

```text
stopped   — workflow выключен, GUI может включить выбранную стратегию
running   — selected / running / owner-rules совпадают
mismatch  — выбрана одна стратегия, а plan/runtime/firewall относятся к другой
partial   — session и firewall расходятся
stale     — runtime state устарел или относится к другому workspace
```

## GUI поведение

Overview теперь показывает GUI-first status вместо обычного CLI-oriented default status. Основная кнопка остаётся one-button start/stop, но рядом добавлена кнопка `Проверить Discord`, которая запускает read-only guided probe из GUI. Если workflow выключен, probe должен вернуть `V0_WORKFLOW_NOT_RUNNING` в текстовом окне GUI, а не отправлять пользователя в shell.

Ручные кнопки `План запуска`, `Подтвердить запуск`, `Команда запуска`, `Команды` перенесены в `Developer mode`. По умолчанию они скрыты.

## CLI для тестов и dev fallback

Добавлена read-only команда:

```text
PYTHONPATH=gui python -m zap2_gui.app --gui-first-overview
```

Developer details:

```text
PYTHONPATH=gui python -m zap2_gui.app --gui-first-overview --gui-first-developer
```

Это не основной пользовательский путь, а проверяемый fallback и контракт для тестов.

## Почему это важно

Предыдущая отладка показала типовой сбой UX: выбранная стратегия была `windows-all-tcp-udp-v3-2-linux-bridge`, но default start-plan мог строиться для `manual-local`, а guided probe запускался при выключенном runtime. Новый overview делает это видимым до теста Discord.

