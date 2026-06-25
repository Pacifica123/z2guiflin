# Stage 8c-r1 — tunnel route diagnosis preflight, deterministic checks

This is the corrected Stage 8c patch. It keeps the Stage 8c feature set and fixes the failed devctl check caused by a host-dependent test assumption.

## Why the previous check failed

The guided-run test expected that `127.0.0.1:10808` was empty while a fake tunnel core was sleeping. On the owner's machine, a real leftover SOCKS/V2Ray listener could still be bound to that port, so the test saw a ready SOCKS endpoint and launched the fake Discord process. The application behavior was plausible for that host state, but the test was not isolated.

## Changes kept from Stage 8c

- Add `--discord-tunnel-route-diagnose` for one short route verdict across tunnel session, local SOCKS, managed Discord launch, recent core logs, recent Discord logs, HTTPS probe reports, and launch preflight reports.
- Detect last-run failures from attached `.zap2` after processes are already stopped, including `TD_LAST_RUN_ROUTED_BUT_UPSTREAM_TLS_CLOSED`.
- Add optional HTTPS-over-SOCKS launch preflight to `--discord-launch-through-socks`.
- Make GUI Discord launch use preflight before spawning Flatpak/Electron.
- Add the `Диагноз маршрута` button in the Tunnel GUI.
- Fix duplicate `@property` on `VlessImportPreview.valid_count`.

## Check fix

- `test_guided_run_auto_prepares_confirms_starts_and_blocks_launch_when_socks_is_not_ready` now uses an isolated unused local TCP port instead of the default `10808`, so a real user tunnel cannot contaminate the test result.

## Local checks

```bash
python tools/gui_checks/inventory_core.py --check
python tools/gui_checks/check_project_tree.py
PYTHONPATH=gui python -m pytest tests/test_stage7p1_discord_tunnel.py tests/test_stage7p5_discord_tunnel_guided.py tests/test_gui_shell_skeleton.py tests/test_stage7z_launch_composer.py tests/test_core_inventory_and_build_map.py -q
PYTHONPATH=gui python -m pytest tests/test_documentation_language.py tests/test_v04_alpha_patch_roadmap.py -q
PYTHONPATH=gui python -m zap2_gui.app --discord-tunnel-route-diagnose
PYTHONPATH=gui python -m zap2_gui.app --discord-proxy-route-plan
```
