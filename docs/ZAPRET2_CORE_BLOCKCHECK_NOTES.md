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
