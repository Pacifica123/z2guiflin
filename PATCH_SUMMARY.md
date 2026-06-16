# v0.4-alpha Stage 7p5 — Guided Discord SOCKS/VLESS tunnel experiment

Stage 7p5 extends the Stage 7p1-7p4 tunnel MVP into a more usable experiment lane.
It keeps the same security boundary: Zap2GUIfLin does not implement VLESS itself,
does not download external cores, does not mutate firewall/service state, and does
not require sudo for SOCKS mode.

## Added

- `--discord-tunnel-https-probe`: harmless HTTPS `HEAD` through the managed local
  SOCKS listener, with JSON report under `.zap2/tunnel/reports`.
- `--discord-tunnel-guided-run`: one-command owner/user-space flow that prepares
  and confirms the tunnel start plan, starts the external core, runs SOCKS and
  HTTPS probes, launches Discord through SOCKS candidates, and writes a guided
  report.
- `--discord-updater-result passed|stuck|unknown` and `--tunnel-observe-seconds`
  for recording updater outcomes without pretending the CLI can see the desktop
  UI by itself.
- `socks-env-only` and `socks-flag-only` Discord launch modes for comparing proxy
  environment variables against the Electron/Chromium proxy flag.
- `--discord-tunnel-tun-plan`: plan-only TUN/TProxy research note; it applies no
  nftables rules and starts no service.
- A lightweight PyQt `Туннель` tab for redacted connection profiles, tunnel
  status, SOCKS probe, HTTPS probe, and TUN/TProxy plan access.

## Updated

- GUI navigation now includes a dedicated `Туннель` section.
- Discord tunnel docs and v0.4-alpha roadmap include Stage 7p5 usage notes.
- The tunnel stage marker is advanced to `v0.4-alpha_stage7p5`.

## Safety notes

- No user VLESS URI is committed to project files.
- External core binaries are still supplied manually by the owner via
  `--tunnel-core-binary` or `ZAP2_TUNNEL_CORE`.
- Guided SOCKS mode auto-confirms only the local user-space tunnel plan. It does
  not use sudo, nftables, NFQUEUE, systemd, or hidden downloads.
- Final updater verdict remains owner-observed: the program records `passed`,
  `stuck`, or `unknown`, while automatic probes measure tunnel readiness.

## Checks

- `PYTHONPATH=gui python -m pytest tests/test_gui_shell_skeleton.py tests/test_stage7p0_discord_tunnel_plan.py tests/test_stage7p1_discord_tunnel.py tests/test_stage7p5_discord_tunnel_guided.py -q`
- `python -m compileall -q gui tests`
