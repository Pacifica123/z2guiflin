# v0.4-alpha Stage 7g — Discord endpoint discovery and diagnostics UI cleanup

This patch pivots the Discord desktop investigation away from guessing only updater domains.

## Added

- `gui/zap2_gui/adapters/discord_endpoint_discovery.py`
- CLI:
  - `--discord-endpoint-plan`
  - `--discord-endpoint-watch --discord-endpoint-seconds N`
  - `--discord-endpoint-report`
- `docs/DISCORD_ENDPOINT_DISCOVERY.md`
- Blockcheck Lab `Endpoints` action that prints the plan plus latest saved report.

## Behavior

The watch samples local `ss -H -tunp` and `pgrep -af [Dd]iscord` output while the owner starts Discord manually. It is read-only: no sudo, no firewall/service mutation, no payload capture and no credentials.

Snapshots are saved under:

```text
.zap2/discord-discovery/
```

## UI cleanup

The diagnostics window is made roomier again and the Blockcheck Lab controls are centered/bounded instead of stretching across the full window. Hint rows and output height were increased to reduce the cramped look on the diagnostics tab.

## Not done

This patch does not implement full one-strategy record-holder validation and does not claim Discord desktop works. It gives the next patch actual local updater endpoint evidence.
