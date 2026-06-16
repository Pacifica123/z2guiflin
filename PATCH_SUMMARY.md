# v0.4-alpha Stage 7p0 — Discord SOCKS/VLESS tunnel technical plan

Stage 7p0 adds a documentation-only plan for a new Discord tunnel lane alongside
the current zapret/nfqws2 strategy lane.

## Added

- `docs/DISCORD_TUNNEL_SOCKS_VLESS_PLAN.md`
  - explains the tunnel philosophy;
  - defines connection profile selection;
  - specifies SOCKS-first runtime design;
  - treats update-only as a single proxied launch window, not proxy-then-restart;
  - defines CLI/GUI/runtime stages and safety boundaries.
- `docs/V2RAYNG_REFERENCE_NOTES.md`
  - records inspected v2rayNG reference concepts;
  - documents the GPL-3.0/reference-only boundary;
  - maps Android concepts to Zap2-specific Linux runtime ideas.
- `references/external/snippets/stage7p0-v2rayng-socks-vless-notes.txt`
  - short reference digest for future implementation patches.
- `tests/test_stage7p0_discord_tunnel_plan.py`
  - checks that the plan exists;
  - checks that the owner-provided sample UUID/IP are not committed;
  - checks that v2rayNG remains reference-only.
- `docs/V04_ALPHA_PATCH_ROADMAP.md` updated with the Stage 7p0 lane.

## Safety

- No external binaries are downloaded or executed.
- No firewall, service, nftables, or NFQUEUE state is changed.
- No Discord process is launched.
- No raw user VLESS connection string is stored in the repository.
- v2rayNG is used as a conceptual reference only; no Android/Kotlin code is copied.
