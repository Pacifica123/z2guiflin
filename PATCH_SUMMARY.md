# v0.4-alpha Stage 7k — community v2 seed and diagnostics layout repair

This patch follows the owner test where the Stage 7j community bridge made YouTube work but did not move Discord desktop past `Checking for updates`.

## Changes

- Add `community-discord-syndata-edge-flow-v2` as an owner-selectable experimental strategy.
- Keep the Stage 7j community bridge intact.
- Add explicit Discord edge phase-zero branches:
  - `payload=empty` + `send:tcp_md5` on observed Discord Cloudflare edge IPs;
  - `syndata:blob=fake_default_tls` on the same edge IPs;
  - host-based Discord `hostfakesplit_multi` branches after the phase-zero attempts;
  - retained YouTube TCP/QUIC fallback.
- Document the observed split result in `docs/DISCORD_COMMUNITY_EDGE_FLOW_RESULTS.md`.
- Repair Blockcheck Lab layout by putting the page into a scroll area, reducing fixed widths, shrinking the output minimum height and increasing the main window default size.

## Boundaries

- This does not claim that Discord is fixed.
- This does not port WinDivert `--wf-*` or Windows raw filters directly.
- This does not touch Stage 8 voice/UDP scope.
- The new strategy must be selected manually and started through the usual owner-confirmed Default workflow.
