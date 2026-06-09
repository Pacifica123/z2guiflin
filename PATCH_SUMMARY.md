# v0.4-alpha Stage 7h — Discord updater endpoint deep discovery

Stage 7h deepens the Discord endpoint discovery pivot introduced in Stage 7g.

## Changes

- Endpoint watcher now samples TCP/UDP socket state and timers with `ss -tanop` / `ss -uanop`.
- Snapshot JSON schema records `state`, `timer`, `sightings`, DNS map and hostname matches.
- Reports now highlight `SYN-SENT` as a pre-TLS TCP connectivity blocker.
- DNS map resolves known Discord targets and matches observed IPs back to likely hostnames.
- Discord updater phase now prioritizes the observed metadata host `updates.discord.com`, while keeping `stable.dl2.discordapp.net` as a fallback alternative.
- Added privacy-aware `--discord-netlog-plan` for optional owner-run Chromium netlog diagnostics.

## Safety

The endpoint watcher remains read-only: no sudo, no firewall/service mutation and no packet payload capture. The netlog helper is a plan only and warns that raw Chromium netlogs may contain sensitive information.
