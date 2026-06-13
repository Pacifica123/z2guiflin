# Patch summary — v0.4-alpha Stage 7n

Stage 7n adds Discord pre-TLS observability groundwork after the RA methodology review.

## Added

- `capturePolicy` metadata on workspace strategies.
- owner-confirmed nft rules now include counters.
- early-flow capture policy support for explicit Discord edge IPs and TCP ports.
- optional diagnostic input SYN+ACK / FIN/RST queue rules for capture policies.
- `community-discord-pretls-diagnostic-pktdebug` strategy.
- `--runtime-nft-state` read-only CLI snapshot.
- `docs/DISCORD_PRETLS_OBSERVABILITY.md`.

## Not changed

- YouTube baseline remains the default strategy path.
- No automatic firewall/service mutation is introduced.
- Voice/UDP remains reserved for Stage 8.


### v0.4-alpha Stage 7n1 — active pre-TLS state probe

Adds active nft/NFQUEUE state reporting for Discord pre-TLS diagnostics: running/applied strategy, session PID health, corrected nft counter commands, and a read-only `--runtime-pretls-probe` checklist.
