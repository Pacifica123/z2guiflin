# Zapret2 core notes for Discord Blockcheck work

This document records the core-level observations used during the v0.4-alpha Discord desktop investigation. It is not a new runtime preset.

## Custom blockcheck lists

The bundled `core/zapret2/blockcheck2.d/custom/README.txt` describes a simple strategy-list tester. The key detail for our GUI is that strategy list files can be overridden through environment variables:

```text
LIST_HTTP
LIST_HTTPS_TLS12
LIST_HTTPS_TLS13
LIST_QUIC
```

This is the safest bridge for a future real one-strategy tournament runner: export one `nfqws2` command into a temporary custom list, point upstream blockcheck at that list, and validate the same candidate through Discord phases instead of collecting a large unrelated bucket of strategies per domain.

## Profile ordering matters

The upstream manual explains that `nfqws2` profiles are selected sequentially and that only the first matching profile wins. It also notes that filters such as L7 and hostlists may become known later, causing profile rediscovery/jump behavior.

For Zap2 this means a future Discord runtime profile must not be assembled as random broad fragments. If we later split updater/app/gateway/CDN/voice into separate profiles, their filters and order must be explicit and tested. A broad TCP/443 hostlist profile placed too early can shadow a more specific Discord media or updater profile.

## Flowseal/Windows translation boundary

Flowseal and Windows GUI presets are useful as reference material, but their commands are not directly executable by the Linux zapret2 runtime. They use Windows interception (`WinDivert`, `--wf-*`) and zapret1-style `--dpi-desync-*` options. For Linux zapret2, the comparable runtime surface is `nfqws2` with Lua `--lua-desync=*` functions, protocol filters, hostlists and nft/iptables NFQUEUE interception.

The practical ideas worth carrying forward are:

```text
- Discord media can need non-443 HTTPS-like TCP ports such as 2053/2083/2087/2096/8443.
- Discord UDP/voice is a separate STUN/Discord L7 layer and stays outside non-voice Stage 7.
- Fake/fakedsplit/fakeddisorder-style strategies correspond conceptually to zapret2 Lua fake/fakedsplit/fakeddisorder/multisplit/multidisorder functions, but must be tested through blockcheck2 rather than copied blindly.
```

## Stage 7g endpoint discovery pivot

The Stage 7f evidence showed a practical limit of target guessing: `stable.dl2.discordapp.net` and `updates.discord.com` can both fail the bounded updater phase in a given run, while the real Electron updater splash may still be connecting somewhere else.

Before adding more guessed updater domains, Stage 7g adds a read-only endpoint discovery loop around the local process:

```text
ss -H -tunp + pgrep -af [Dd]iscord
```

This does not replace Blockcheck. It is a source of candidate endpoints that can later be converted into service targets, hostlist entries or explicit phase alternatives.

If the discovery output contains UDP endpoints during `Checking for updates`, the v0.4 plan must explicitly decide whether to investigate that as a pre-voice bootstrap layer or keep it out of the non-voice success criteria.

## Stage 7h: updater socket state discovery

Stage 7h extends the Stage 7g endpoint discovery loop with TCP state/timer evidence and best-effort DNS mapping. The owner observed the Discord updater splash opening a TCP/443 socket in `SYN-SENT` toward a Cloudflare edge IP that resolves in the current environment for `updates.discord.com`. This means the failure is visible before a completed TLS/HTTP request on that socket, so more curl/TLS strategy tournaments against later Discord phases are not the next best diagnostic step.

New CLI helpers:

```bash
PYTHONPATH=gui python -m zap2_gui.app --discord-endpoint-watch --discord-endpoint-seconds 30
PYTHONPATH=gui python -m zap2_gui.app --discord-endpoint-report
PYTHONPATH=gui python -m zap2_gui.app --discord-netlog-plan
```

The watcher remains read-only: it samples `ss`, `pgrep` and DNS metadata, does not use sudo, does not mutate firewall/services and does not capture packet payloads. The optional netlog plan is not executed automatically because Chromium netlogs can contain privacy-sensitive URLs, headers or token-like values.

### v0.4-alpha Stage 7i — Discord DNS edge diagnosis

Stage 7i переносит идею Windows GUI DNS-проверок в read-only Linux diagnostic. Команды `--discord-dns-edge-plan` и `--discord-dns-edge-check` сравнивают system/Cloudflare/Google/Quad9/AdGuard/OpenDNS resolvers и проверяют TCP/443 для возвращённых Discord edge IP. Это не меняет DNS и не требует sudo. Если найден `connect-ok` edge, DNS/hosts steering можно рассматривать как owner-confirmed эксперимент. Если все edge IP timeout, то текущий Discord updater blocker шире, чем DNS-подмена, и обычные TLS Blockcheck-стратегии всё ещё не упражняются на SYN-SENT socket.
