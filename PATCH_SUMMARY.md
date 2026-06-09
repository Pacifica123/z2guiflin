# v0.4-alpha Stage 7i — Discord DNS edge diagnosis

Stage 7i answers the owner question about the Windows GUI DNS concept: DNS can help only if another resolver returns a different Discord edge IP that actually completes TCP/443. The patch adds a read-only Linux diagnostic instead of mutating DNS immediately.

## Added

- `gui/zap2_gui/adapters/discord_dns_edge_diagnostics.py`
  - compares system/Cloudflare/Google/Quad9/AdGuard/OpenDNS resolver outputs;
  - TCP-probes returned IPv4 edge addresses on port 443;
  - writes diagnosis snapshots under `.zap2/discord-discovery/`;
  - reports whether DNS/hosts steering is plausible or whether all tested edges timeout before TLS.
- CLI:
  - `--discord-dns-edge-plan`
  - `--discord-dns-edge-check`
  - `--discord-dns-edge-hosts`
  - `--discord-dns-edge-resolvers`
  - `--discord-dns-edge-timeout`
- `docs/DISCORD_DNS_EDGE_DIAGNOSTICS.md`
- `tests/test_stage7i_discord_dns_edge_diagnostics.py`

## Changed

- Discord docs now record the Stage 7i decision branch: connect-ok DNS edge means DNS/hosts steering may be worth an owner-confirmed experiment; all-timeout edges mean the blocker is broader than DNS and ordinary TLS Blockcheck strategies are not exercised yet.
- `tests/test_service_target_presets.py` now matches the Stage 7h updater-first order (`updates.discord.com stable.dl2.discordapp.net`).

## Boundaries

- Does not change system DNS.
- Does not edit `/etc/hosts`.
- Does not require sudo.
- Does not mutate firewall, services or runtime state.
- Does not claim Discord is fixed; it classifies whether the DNS idea is relevant to the observed `SYN-SENT` updater failure.
