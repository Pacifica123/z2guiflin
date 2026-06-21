# Stage 7w — Discord SYN-data v2c matrix

This patch follows the owner-confirmed v2b result: the real runtime args now do
include `discordapp.com`/`www.discordapp.com`, but Flatpak Discord and curl still
stop after TLS ClientHello while loading `https://discordapp.com/app`.

## Added strategies

- `community-discord-syndata-edge-flow-v2c-send-only`
- `community-discord-syndata-edge-flow-v2c-fixed-sni`
- `community-discord-syndata-edge-flow-v2c-no-md5`
- `community-discord-syndata-edge-flow-v2c-host-first`

All four remain owner-selected, plan-only strategies. They preserve the YouTube
fallback lane and do not change firewall/service behavior automatically.

## Diagnostic intent

The matrix isolates the remaining TLS-stage suspect after v2b:

- edge `syndata`/`rndsni` may be stalling ServerHello;
- fixed fake SNI may behave differently from random SNI;
- `tcp_md5` may be unsafe on this Linux route;
- broad Cloudflare edge-IP filters may shadow hostlist-specific Discord webapp
  filters.

## Docs/tests

- Added `docs/DISCORD_SYN_DATA_EDGE_FLOW_V2C_MATRIX.md`.
- Updated the community edge-flow results document.
- Added targeted tests covering catalog registration, runtime-args generation,
  variant differences, diagnostics, and generated session args.
