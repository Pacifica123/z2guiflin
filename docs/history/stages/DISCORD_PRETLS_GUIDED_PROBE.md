# Guided probe Discord до TLS

Статус: owner-run diagnostic. P02 broad-root GUI/project import отключён; privileged counter probe staged до отдельного bounded action.

Guided probe объединяет состояние `nftables`, NFQUEUE, `nfqws2`, counters и ручное окно запуска Discord в один отчёт. Он предназначен для воспроизводимого наблюдения, а не для автоматической починки.

## Команда

```bash
PYTHONPATH=gui python -m zap2_gui.app \
  --runtime-discord-pretls-guided-probe
```

## Требуемое состояние

- выбран диагностический или исследуемый preset;
- Default workflow уже запущен владельцем;
- managed PID жив;
- owned nft table применена;
- номер NFQUEUE совпадает в state и args;
- Discord до начала окна полностью закрыт.

## Правило окна наблюдения

Probe снимает состояние до запуска приложения, печатает `MANUAL ACTION`, после чего владелец открывает Discord. Затем снимаются counters и process/network evidence после окна ожидания.

Probe не должен сам запускать Discord: ручная граница сохраняет понятный момент начала эксперимента и не смешивает lifecycle приложения с privileged diagnostic.

## Поля отчёта

- profile и strategy;
- runtime/session PID;
- queue number;
- nft table/chain/rule state;
- counters before/after/delta;
- endpoint/process observations;
- debug/log delta;
- verdict и причины;
- пути к JSON/Markdown report.

## Основные verdict

```text
READY_FOR_MANUAL_ACTION
NO_MANAGED_SESSION
NFT_STATE_MISSING
QUEUE_MISMATCH
NO_COUNTER_DELTA
CAPTURE_OBSERVED
INSUFFICIENT_PRIVILEGES
```

Точный verdict не означает успех обхода. Например, `CAPTURE_OBSERVED` доказывает попадание трафика в цепочку, но не доказывает продвижение updater.

## Граница

Probe не меняет стратегию, не строит новый preset, не устанавливает правила и не объявляет candidate рабочим без owner evidence.
