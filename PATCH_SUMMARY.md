# Patch summary

## Title

Clarify Tunnel core start UX and xhttp/core mismatch

## What changed

- added a visible `Tunnel core` block in the Tunnel tab;
- added Core binary field and buttons for plan/start/stop/SOCKS probe;
- changed the route hint so `Запустить Discord через SOCKS` no longer looks like it starts the core;
- added xhttp/splithttp compatibility warnings for V2Ray core;
- blocked obviously incompatible `v2ray + xhttp/splithttp` starts before creating a failed session;
- included last core stderr/stdout details in tunnel status, probe, and launch errors;
- added tests for xhttp/core UX and failed-session diagnostics.

## Why

The previous UX told the user to start/probe again even when the real problem was visible in `.zap2/tunnel/logs/default.core.stderr.log`: `unknown transport protocol: xhttp`. The GUI needed to expose the real order and the real failure cause.
