# Наблюдение Discord до TLS

Статус: справка по Stage 7n/7n1.

## Причина

Обычный Blockcheck по TLS не объясняет случай, когда desktop Discord остаётся в `SYN-SENT` или не доходит до полноценного ClientHello. Для такого отказа сначала нужно доказать, что ранние пакеты попадают в Linux NFQUEUE path.

## Что добавлено

- явный `capturePolicy` в стратегии;
- counters owned `nftables` rules;
- read-only snapshot runtime/nft/NFQUEUE;
- диагностическая стратегия `community-discord-pretls-diagnostic-pktdebug`;
- проверка PID и активной стратегии;
- команды для ручного сравнения counters до/после запуска Discord.

## Команды

```bash
PYTHONPATH=gui python -m zap2_gui.app --runtime-nft-state
PYTHONPATH=gui python -m zap2_gui.app --runtime-pretls-probe
```

## Диагностический цикл

```text
runtime stopped baseline
-> выбрать pktdebug strategy
-> start owner workflow
-> snapshot counters
-> открыть Discord
-> повторить snapshot
-> сравнить queue/debug/session state
```

## Интерпретация

Если counters не меняются, проблема находится в capture scope, hook, UID, ports или route. Если counters меняются, но соединение не продвигается, исследуется strategy behavior и ответ удалённой стороны.

## Безопасность

Команды наблюдения не меняют firewall, не запускают Discord и не захватывают payload автоматически. Чтение некоторых counters может потребовать отдельного owner-run с `sudo`.
