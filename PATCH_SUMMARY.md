# v0.4-alpha Stage 7j — community edge-flow bridge and diagnostics UI width fix

Stage 7j reacts to owner evidence that a community Windows preset can make YouTube and Discord work on the same network where the Linux Discord path is stuck before TLS. The patch adds an experimental Linux strategy bridge instead of continuing DNS-only or TLS-only diagnosis.

## Added

- `strategies/community-discord-youtube-edge-flow.json`
  - owner-selectable experimental strategy;
  - Discord Cloudflare edge `ipset-ip` + `wssize/syndata` pre-TLS seed;
  - Discord updater/app/CDN `hostfakesplit_multi` profiles;
  - YouTube TCP/QUIC fallback profiles from the same community preset concept.
- `strategies/imported/community-discord-youtube-edge-flow.txt`
- `strategies/imported/community-discord-youtube-edge-flow.json`
- `core/zapret2/lua/custom_funcs.lua`
  - conservative `hostfakesplit_multi` compatibility shim over built-in `hostfakesplit`.
- `docs/WINDOWS_COMMUNITY_PRESET_PORTING.md`
- `tests/test_stage7j_community_edge_flow_strategy.py`

## Changed

- `strategies/catalog.json` now lists the new experimental strategy.
- Blockcheck Lab layout uses fixed content width/minimum widths so the diagnostics output no longer collapses into a tiny centered column.
- Existing UI layout tests now assert the less-collapsed Stage 7j sizing.

## Boundaries

- The new strategy is not selected automatically.
- No firewall/services are changed during tests.
- WinDivert `--wf-*` options are not executed on Linux.
- Voice/UDP STUN from the community preset is not ported; Stage 8 remains reserved for voice investigation.
