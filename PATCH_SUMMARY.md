# v0.4-alpha Stage 7o2b — baseline row runner endpoint-watch fix

## Why

`--discord-observation-matrix-run-row baseline` crashed after the owner closed Discord because the row runner called `run_discord_endpoint_watch(root, seconds)` with positional arguments, while the endpoint watcher API is keyword-only: `run_discord_endpoint_watch(*, root=..., seconds=...)`.

This made the simplified matrix runner fail before the baseline 45-second observation window could start.

## What changed

- Fixed the baseline row runner to call the endpoint watcher with keyword arguments.
- Updated the row-runner stage marker to `v0.4-alpha_stage7o2b`.
- Added a regression test that injects a keyword-only endpoint runner and verifies the baseline row completes.
- Documented the fix in the row-runner notes/snippet.

## What this does not do

- Does not launch Discord automatically.
- Does not start/stop Zap2 runtime automatically.
- Does not mutate firewall/services.
- Does not add a new Discord bypass strategy.

## Owner-facing retry

```bash
PYTHONPATH=gui python -m zap2_gui.app --discord-observation-matrix-run-row baseline
```

Start with Discord closed and Zap2 runtime stopped. Open Discord only when the runner prints the `MANUAL ACTION WINDOW` prompt.
