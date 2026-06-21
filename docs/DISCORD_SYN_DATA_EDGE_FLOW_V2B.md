# Discord SYN-data edge-flow v2b (v0.4-alpha Stage 7v)

Stage 7v is a narrow follow-up to the owner test of
`community-discord-syndata-edge-flow-v2`.

## Owner evidence that motivated v2b

The v2 test changed the Discord failure mode in a useful way:

```text
before v2:  Discord/Cloudflare edge socket stayed around SYN-SENT / connect timeout
with v2:    Discord Flatpak reached ESTAB on 162.159.130.233:443
next block: https://discordapp.com/app timed out after TLS ClientHello
```

The Flatpak log also showed the concrete webapp URL that failed after update
checks were already disabled/passed:

```text
https://discordapp.com/app?_=...
```

That host was present in the project-level default hostlist, but it was missing
from the runtime strategy hostlist branches that v2 passed to `nfqws2`.

## Strategy added

Stage 7v adds this owner-selectable strategy:

```text
community-discord-syndata-edge-flow-v2b
```

It intentionally keeps the v2 phase-zero branches unchanged:

- `payload=empty` + `out-range=<s1` + `send:tcp_md5` for observed Discord
  Cloudflare edge IPs;
- `out-range=s1<d1` + `syndata:blob=fake_default_tls` for the same edge IPs.

The only network-profile change is host coverage for the observed webapp phase:

```text
discordapp.com
www.discordapp.com
```

Those hosts are added to the Discord hostlist branches, including the
`updates.discord.com`/`discord.com` app branch and the broader Discord host
branch. The YouTube fallback is retained so the owner can keep comparing Discord
behavior against the already-useful YouTube baseline.

## Diagnostic hints exposed by `--show-strategy`

The strategy JSON includes `diagnosticHints`. `--show-strategy` renders them so
that the GUI/CLI can display the current interpretation without executing a
probe:

```bash
PYTHONPATH=gui python -m zap2_gui.app \
  --show-strategy community-discord-syndata-edge-flow-v2b
```

The hint block records:

- observed URL: `https://discordapp.com/app`;
- required hostlist hosts: `discordapp.com`, `www.discordapp.com`;
- phase ladder: `SYN-SENT -> ESTAB -> TLS ClientHello -> TLS ServerHello -> HTTP/`;
- owner-observed v2 split: phase-zero helped TCP, host/SNI phase still timed out
  after ClientHello.

## Manual check after selecting v2b

After selecting v2b and starting the confirmed Default workflow, watch whether
Discord moves past the current TLS plateau:

```bash
watch -n 0.2 "ss -tanp | grep -E '162\\.159\\.130\\.233:443|SYN-SENT|ESTAB'"
```

Then compare the direct curl ladder:

```bash
curl -4vk --connect-timeout 8 --max-time 20 \
  --resolve discordapp.com:443:162.159.130.233 \
  https://discordapp.com/app -o /dev/null
```

Desired next improvement:

```text
TLS ServerHello appears, or HTTP/ appears.
```

Still-bad but informative result:

```text
ESTAB remains, TLS ClientHello is sent, and ServerHello/HTTP never appears.
```

If that persists, the next branch should not be another hostlist-only tweak. It
should compare either a different TLS-phase desync profile or a route/tunnel/TUN
lane, because v2 already demonstrated that phase-zero can affect TCP but not yet
complete the HTTPS webapp load.
