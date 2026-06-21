# Discord community edge-flow results (v0.4-alpha Stage 7k)

Stage 7j proved a useful split result from the owner test:

- `community-discord-youtube-edge-flow` helped YouTube on the same Linux runtime path.
- The same strategy did not move Discord desktop beyond `Checking for updates`.
- Endpoint discovery still points at Discord Cloudflare edges in `SYN-SENT`, before TLS/HTTP payload strategies are exercised.

This means the runtime bridge is not generally broken: nftables queueing, nfqws2 startup, strategy selection and YouTube hostlist handling are working well enough to affect browser traffic. The remaining Discord failure is narrower: the Linux Discord newUpdater path still needs a closer equivalent of the Windows preset's early-flow behavior.

## Stage 7k v2 seed

Stage 7k adds an explicit owner-selectable strategy:

```text
community-discord-syndata-edge-flow-v2
```

It differs from the Stage 7j bridge by making the Discord edge phase-zero branch more explicit:

- first branch: `payload=empty` + `out-range=<s1` + `send:tcp_md5` on observed Discord Cloudflare edge IPs;
- second branch: `out-range=s1<d1` + `syndata:blob=fake_default_tls` on the same edge IPs;
- later branches retain the host-based Discord `hostfakesplit_multi` and YouTube fallback profiles.

This still is not a direct WinDivert port. Windows `--wf-*` and raw filter parts remain Windows-only. The purpose is to test whether Linux nfqws2 can affect the SYN-stage path that currently blocks the updater.

## How to read the next owner test

After selecting `community-discord-syndata-edge-flow-v2`, start the Default workflow and run endpoint discovery while Discord is on the splash screen.

Good sign:

```text
SYN-SENT disappears or turns into ESTAB, and the splash moves past Checking for updates.
```

Bad sign:

```text
SYN-SENT remains on the same 162.159.* edge IPs.
```

If the bad sign persists, the next investigation should focus on nft hook scope/priority, whether nfqws2 sees the Discord SYN packets at all, and which exact Windows early-flow primitive is missing from the Linux bridge.

## Stage 7l.1 runtime args-file startup fix

`community-discord-syndata-edge-flow-v2` uses early-flow arguments containing `<`, for example `--out-range=<s1`. Upstream `nfqws2` parses `@args` files through shell-like expansion, so these tokens must be quoted in the generated args file. Stage 7l.1 makes that writer shell-safe and changes the default public runtime input base to a uid-scoped temp directory so devctl checks are not affected by stale root-owned `/tmp/zap2-runtime-inputs` directories.

## Stage 7m 5222 follow-up

A second owner-provided Discord-only community preset exposed TCP `5222` in its Windows `--wf-tcp-out` capture envelope. Because Linux does not execute WinDivert `--wf-*` options, Stage 7m adds `community-discord-hostfakesplit-5222-minimal` with `5222` made explicit in `--filter-tcp`. This is intentionally a separate strategy so owner tests can compare the mixed Discord+YouTube bridge, the v2 phase-zero seed and the clean Discord-only 5222 seed without changing defaults.


## Stage 7v v2b follow-up

A later owner retest of `community-discord-syndata-edge-flow-v2` showed a real
phase shift: the Flatpak Discord socket reached `ESTAB` on
`162.159.130.233:443`, but the webapp then failed to load
`https://discordapp.com/app?...` with `ERR_TIMED_OUT` after TLS ClientHello.

Stage 7v therefore adds `community-discord-syndata-edge-flow-v2b`, a small
strategy variant that keeps the v2 phase-zero branches but adds
`discordapp.com` and `www.discordapp.com` to Discord hostlist branches. The
expected diagnostic ladder is now:

```text
SYN-SENT -> ESTAB -> TLS ClientHello -> TLS ServerHello -> HTTP/
```

The purpose of v2b is to check whether the missing webapp host was the next
blocking detail after v2 moved the failure from TCP connect timeout to TLS
ClientHello timeout. If v2b still stops at `ESTAB` + `TLS ClientHello`, the next
suspect is no longer host coverage alone.

## Stage 7w — v2c phase-zero matrix

Owner testing of the corrected v2b runtime confirmed that `discordapp.com` and
`www.discordapp.com` were present in `.zap2/runtime/sessions/default.nfqws2.args`.
However, both `curl --resolve discordapp.com:443:162.159.130.233` and Flatpak
Discord still timed out after TLS ClientHello while loading
`https://discordapp.com/app?...`.

Stage 7w therefore adds four manual, owner-selected matrix branches:

- `community-discord-syndata-edge-flow-v2c-send-only`;
- `community-discord-syndata-edge-flow-v2c-fixed-sni`;
- `community-discord-syndata-edge-flow-v2c-no-md5`;
- `community-discord-syndata-edge-flow-v2c-host-first`.

These branches do not claim to fix Discord. They isolate whether the remaining
blocker is the edge `syndata` phase, `rndsni`, `tcp_md5`, or filter ordering
between hostlist and Cloudflare edge-IP branches.
