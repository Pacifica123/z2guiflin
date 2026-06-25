# Stage 8b — tunnel launch lifecycle guard

This patch fixes the failure mode observed after Stage 8a: Flatpak Discord was launched with the SOCKS proxy flag, but the managed VLESS/SOCKS tunnel had already been stopped or was not listening anymore, so Electron returned `ERR_PROXY_CONNECTION_FAILED` and kept retrying in the parent terminal.

## Changes

- Treat zombie PIDs as not running in tunnel status/probe/launch checks.
- Store explicit tunnel session state (`running`, `failed`, `stopped`, `stale`) and require `state=running` before launching Discord through SOCKS.
- Require a minimal SOCKS5 no-auth handshake before spawning Discord. If the local proxy is not ready, the adapter blocks the launch instead of creating an Electron retry loop.
- Redirect launched Discord stdout/stderr to `.zap2/tunnel/logs/default.discord.stdout.log` and `.zap2/tunnel/logs/default.discord.stderr.log`.
- Add `--discord-stop-launched` plus a GUI `Остановить Discord launch` button to stop only the recorded Discord process group.
- Preserve VLESS Reality stream settings (`sni`, `fp`, `pbk`, `sid`, `spx`, `alpn`) in generated core config. The previous generator set `security=reality` but did not write `realitySettings`, which made imported Reality profiles incomplete.
- Update docs and tests for the safer launch lifecycle.

## Local checks

```bash
python tools/gui_checks/inventory_core.py --check
python tools/gui_checks/check_project_tree.py
PYTHONPATH=gui python -m pytest tests/test_core_inventory_and_build_map.py tests/test_stage7p1_discord_tunnel.py tests/test_stage7p5_discord_tunnel_guided.py tests/test_stage7z_launch_composer.py tests/test_gui_shell_skeleton.py -q
PYTHONPATH=gui python -m pytest tests/test_documentation_language.py tests/test_v04_alpha_patch_roadmap.py tests/test_gui_shell_skeleton.py -q
PYTHONPATH=gui python -m zap2_gui.app --discord-proxy-route-plan
PYTHONPATH=gui python -m zap2_gui.app --discord-stop-launched
```
