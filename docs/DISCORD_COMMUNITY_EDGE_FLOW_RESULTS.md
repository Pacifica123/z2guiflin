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
