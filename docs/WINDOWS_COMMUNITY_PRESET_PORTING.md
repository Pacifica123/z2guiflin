# Stage 7j — Windows community preset porting notes

The owner reported that a community Windows preset helped both YouTube and Discord on the same network/device class where the current Linux `discord-desktop` Blockcheck path reaches `SYN-SENT` timeouts against Discord Cloudflare edges.

## What was relevant in the preset

The useful Discord pieces are not the DNS selector itself. They are the early/broad runtime ideas:

- wide WinDivert capture: `--wf-tcp-out=80,443-65535` and `--wf-udp-out=80,443-65535`;
- hostname cache: `--ipcache-hostname=1`;
- Discord updater/app/CDN profiles using `hostfakesplit_multi` for `updates.discord.com`, `discord.media` and the Discord hostlist;
- YouTube profiles that combine TCP split/disorder and UDP QUIC fake traffic.

## Linux translation limits

This patch does not copy WinDivert behavior literally. Linux runtime still uses owner-confirmed nftables NFQUEUE rules and the vendored `nfqws2` binary. The bridge therefore translates concepts, not command-line flags:

- WinDivert `--wf-*` options are omitted from `runtimeArgs`.
- The strategy uses `--filter-tcp`/`--filter-udp` to tell the existing runtime apply plan which ports must be queued.
- `hostfakesplit_multi` is provided by a conservative project-local Lua shim, currently mapping `hosts=a,b` to the first host for built-in `hostfakesplit` compatibility.
- Discord Cloudflare edge IPs observed during Stage 7h/7i are included as an experimental `--ipset-ip` pre-TLS profile with `wssize` + `syndata`.

## Why the pre-TLS profile exists

Stage 7h/7i showed that the desktop Discord updater can stall before TLS: sockets remain in `SYN-SENT`, and all tested DNS resolvers returned Discord Cloudflare edge addresses that timed out on TCP/443. Ordinary TLS ClientHello strategies are not exercised on such sockets.

The `community-discord-youtube-edge-flow` strategy therefore includes an experimental first profile scoped to the observed Discord Cloudflare edge IPs:

```text
--filter-tcp=443
--ipset-ip=<observed Discord Cloudflare edges>
--out-range=-s1
--lua-desync=wssize:wsize=1:scale=6
--lua-desync=syndata:blob=fake_default_tls
```

This is a hypothesis copied from the core documentation direction: techniques that must affect the earliest packets need to be ordered before later data/TLS split functions.

## Safety boundary

The strategy is catalog data only until the owner explicitly selects it and runs the existing Default workflow with plan/confirmation. It does not auto-start, does not mutate firewall/services during checks and does not import the Windows voice/STUN block.
