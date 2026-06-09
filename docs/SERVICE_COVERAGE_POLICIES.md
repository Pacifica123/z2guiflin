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
1. updates.discord.com
2. stable.dl2.discordapp.net
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
