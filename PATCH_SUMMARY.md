# v0.4-alpha Stage 7v — Discord SYN-data edge-flow v2b

Owner testing of `community-discord-syndata-edge-flow-v2` showed a useful phase
shift: Discord Flatpak reached `ESTAB` on `162.159.130.233:443`, but the main
webapp load then timed out after TLS ClientHello while opening
`https://discordapp.com/app?...`.

Stage 7v adds a narrow v2b experiment for that next phase.

## Updated

- Added owner-selectable strategy `community-discord-syndata-edge-flow-v2b`.
- Kept the v2 phase-zero branches unchanged: `payload=empty`/`send:tcp_md5` and
  `syndata` on observed Discord Cloudflare edge IPs.
- Added `discordapp.com` and `www.discordapp.com` to Discord hostlist branches
  so the observed Flatpak webapp URL is covered by the strategy runtime args.
- Preserved the YouTube fallback profile for side-by-side baseline checks.
- Added optional `diagnosticHints` support to workspace strategies.
- Extended `--show-strategy` output with the v2b diagnostic ladder:
  `SYN-SENT -> ESTAB -> TLS ClientHello -> TLS ServerHello -> HTTP/`.
- Documented the owner evidence, manual checks, and expected next outcome in
  `docs/DISCORD_SYN_DATA_EDGE_FLOW_V2B.md`.
- Updated community edge-flow result notes with the v2 -> v2b reasoning.

## Safety

- Strategy remains plan-only and owner-selectable.
- No automatic execution, sudo, service mutation, or firewall mutation is added.
- Runtime apply/revert remains owner-confirmed through the existing Default
  workflow.

## Checks

- `PYTHONPATH=gui python -m py_compile gui/zap2_gui/models/strategy.py gui/zap2_gui/adapters/workspace_profiles.py`
- `PYTHONPATH=gui python -m pytest -q tests/test_stage7v_discord_syndata_v2b.py tests/test_stage7k_ui_and_community_v2.py tests/test_stage7m_discord_5222_seed.py tests/test_workspace_profiles_and_strategies.py`
- `PYTHONPATH=gui python -m zap2_gui.app --show-strategy community-discord-syndata-edge-flow-v2b`

Note: a full-suite probe still hits the pre-existing stale `CORE_INVENTORY.json`
versus vendored `core/zapret2/lua/custom_funcs.lua` mismatch in the provided
baseline archive. This patch does not touch vendored core inventory.
