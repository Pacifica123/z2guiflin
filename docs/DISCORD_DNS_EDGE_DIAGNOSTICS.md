# Discord DNS edge diagnostics

Stage 7i проверяет идею из Windows GUI DNS-раздела в безопасном Linux-формате: не менять DNS сразу, а сначала понять, может ли смена резолвера вообще помочь Discord desktop.

## Почему это нужно

Owner-run показал, что Discord Linux `newUpdater` на экране `Checking for updates` открывает TCP/443 socket к Cloudflare edge IP, который текущий DNS сопоставляет с `updates.discord.com`/`discord.com`, и socket остаётся в `SYN-SENT`. Отдельные `nc`/`curl --resolve` проверки показали timeout по всем A-record IP для `discord.com`, `updates.discord.com`, `cdn.discordapp.com`, `gateway.discord.gg` и `discord.gg` в текущем окружении.

Это означает pre-TLS blocker: TCP handshake не завершается, поэтому обычные `tls_client_hello`, `fake`, `multidisorder`, `seqovl` и другие TLS/HTTP Blockcheck-стратегии ещё не получают полезный payload на этом socket.

## Где здесь DNS

Windows GUI умеет работать с разными DNS-провайдерами. Для Linux v0.4-alpha Stage 7i этот принцип пока не портируется как системная настройка. Вместо этого добавлена read-only диагностика:

```bash
PYTHONPATH=gui python -m zap2_gui.app --discord-dns-edge-plan
PYTHONPATH=gui python -m zap2_gui.app --discord-dns-edge-check
```

Команда сравнивает системный resolver и несколько публичных resolver families, затем пробует TCP/443 connect к возвращённым IPv4 edge IP. Она не требует sudo, не меняет `/etc/resolv.conf`, не трогает `hosts`, nftables, systemd или runtime state.

## Как читать результат

Если хотя бы один resolver вернул IP, который соединяется на TCP/443, то DNS/hosts steering может быть отдельной owner-confirmed веткой: например, временно направить `updates.discord.com` на рабочий edge и повторить запуск Discord.

Если все resolver-ы возвращают только timeout edges, то смена DNS сама по себе почти наверняка не решит проблему. В таком случае blocker шире, чем DNS poisoning: это routing/IP/TCP-level доступность Cloudflare edge, и проект должен честно отделять её от TLS-oriented zapret стратегий.

## Связь с v0.4 Discord cycle

Stage 7i не оживляет Discord автоматически. Он добавляет критерий решения:

```text
connect-ok edge exists -> DNS/hosts steering may be useful
all edges timeout -> DNS concept is not enough; continue pre-TLS branch or record blocker
```

Это помогает не возвращаться в бесконечный tournament по `gateway`/CDN, пока updater phase даже не завершает TCP handshake.
