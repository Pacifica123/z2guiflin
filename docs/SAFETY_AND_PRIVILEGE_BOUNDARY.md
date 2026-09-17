# Граница безопасности и привилегий

## Базовая позиция

До `v1-stable` гарантированный пользователь — владелец/разработчик. Поэтому продукт должен предпочитать движение вперёд и прозрачный локальный контроль чрезмерному UX-патернализму.

Это не разрешение на скрытую системную мутацию. Это решение не блокировать разработку только потому, что домен будущего продукта включает привилегированные Linux-операции.

## Что могут делать автоматические патчи

Автоматические devctl-проверки могут:

- парсить Python files;
- проверять структуру репозитория;
- читать vendored metadata;
- валидировать наличие документации и исходников;
- запускать pure unit tests для нашего кода.

Автоматические проверки не должны:

- вызывать `sudo`;
- устанавливать пакеты;
- запускать upstream installer scripts;
- менять system services;
- менять состояние firewall/nftables/iptables;
- скачивать executable content из сети.

## Что владелец может делать локально

Владелец может запускать привилегированные команды локально, когда будущая документация или GUI формирует понятный план. Такие действия должны считаться owner-confirmed development operations, а не assistant-side automation.

Будущие privileged workflows должны иметь такую форму:

```text
collect facts -> generate command plan -> show exact plan -> owner confirms -> run locally -> log result -> offer rollback notes
```

## Принцип отсутствия remote bootstrap

Продукт не должен зависеть от `curl | sh`, слепых remote installers или автоматической замены upstream. Исходники ядра лежат vendored в `core/zapret2/` и обновляются только явными source-import patches.

## Практическое отношение к безопасности

Безопасность для этого проекта означает:

- видимые границы;
- минимум скрытого состояния;
- локальное владение исходниками;
- воспроизводимые патчи;
- логи и отчёты;
- отказ запускать привилегированные команды внутри среды ассистента;
- уважение к способности владельца управлять собственной development machine.

## Stage 8: runtime contracts без исполнения

Stage 8 добавляет runtime lifecycle contracts, но не меняет privilege boundary. Автоматические проверки могут валидировать JSON-схемы, example plans, events и confirmations, однако не могут запускать `nfqws2`, `make`, `sudo`, firewall tools или `systemd`.

Будущий privileged runtime должен пройти через цепочку:

```text
plan -> owner confirmation -> execution -> log -> rollback/revert
```

Если будущий патч добавляет настоящий executor, он должен отдельно объяснить, какие действия требуют привилегий, где сохраняется runtime state, как владелец подтверждает конкретный plan hash и как выполняется точечный откат.


## Security blocklist boundary

Threat-IP blocking живёт в отдельной workspace-owned nft table и не переиспользует zapret NFQUEUE ownership. Списки являются внешними данными, не вендорятся и обновляются только через HTTPS с полной валидацией до atomic cache replacement. Network failure не очищает last-known-good cache. Inbound policy по умолчанию выключена; outbound policy ограничивается UID владельца.

Periodic systemd timer устанавливается только явной root-командой после того, как owner создал локальный config. Автоматические devctl tests не выполняют download, `nft` или `systemctl`; они используют fake fetcher/runner.
