# v0.4-alpha Stage 7p1-7p4 — Experimental Discord SOCKS/VLESS tunnel MVP

Stage 7p1-7p4 implements the first practical pieces of the Stage 7p0 tunnel
plan.  Zap2GUIfLin can now import owner-supplied VLESS share links, keep them as
redacted tunnel connection profiles, generate a local loopback SOCKS core config
for an external core, start/stop that core through an owner-confirmed plan, probe
the local SOCKS readiness, and launch Discord with SOCKS proxy candidates.

## Added

- `gui/zap2_gui/adapters/discord_tunnel.py`
  - VLESS URI parser and redacted profile model.
  - `.zap2/tunnel` storage for secret connection profiles.
  - Active connection selection.
  - Xray/V2Ray-style VLESS + loopback SOCKS config generator.
  - External core binary detection (`xray`, `v2ray`, `sing-box`, or explicit path).
  - Owner-confirmed tunnel start plan saved in `.zap2/runtime/plans`.
  - Managed core start/stop/session/probe helpers.
  - Discord launch wrapper using proxy env vars and `--proxy-server`.
- CLI commands:
  - `--tunnel-connection-import-vless URI_OR_@FILE`
  - `--tunnel-connections`
  - `--tunnel-select-connection CONNECTION_ID`
  - `--discord-tunnel-plan`
  - `--discord-tunnel-start --confirm PLAN_ID`
  - `--discord-tunnel-status`
  - `--discord-tunnel-probe`
  - `--discord-tunnel-stop`
  - `--discord-launch-through-socks`
- Docs updated with implementation status and v2rayNG reference-only usage.
- Tests for parsing, redaction, generated config, plan/confirm/start/stop, and
  secret non-leakage.

## Safety

- No external core is downloaded automatically.
- No v2rayNG Kotlin code is copied.
- Raw owner VLESS data is not printed in normal CLI output or stored in project
  files.
- Secret runtime files are under `.zap2/tunnel` with restrictive permissions where
  supported.
- SOCKS binds to `127.0.0.1` only.
- Tunnel start refuses to mix with an already-running default zapret workflow.
- Stop targets only the recorded managed core PID.
- Firewall, nftables, systemd, and NFQUEUE state are not modified by this lane.

## Known limits

- The first generator primarily targets VLESS TCP + `security=none` + optional
  HTTP header host, matching the owner's sample class.
- `--discord-tunnel-probe` checks process and loopback port readiness; a full
  through-SOCKS HTTPS probe is planned for Stage 7p5.
- Discord updater success is still manually observed after `--discord-launch-through-socks`.
- GUI integration and TUN/TProxy are not included yet.
