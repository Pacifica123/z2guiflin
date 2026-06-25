# Stage 8a — SOCKS route diagnostics for Flatpak Discord

This patch responds to owner logs where the VLESS core was running and receiving
local SOCKS connections, but Flatpak Discord still timed out on
`https://discordapp.com/app`.

## Diagnosis captured by the patch

A managed VLESS tunnel opens a local listener such as `socks5://127.0.0.1:10808`.
That is not a transparent route. Discord, Firefox, Telegram, and Flatpak apps do
not start using it unless they are launched or configured with proxy settings.

The logs also showed many `proxy/socks: insufficient header > EOF` lines. Those
are consistent with clients/probes opening the SOCKS port and closing without a
complete SOCKS greeting. They do not by themselves prove that the tunnel is dead.

## Runtime/CLI changes

- `--discord-tunnel-probe` now performs a minimal SOCKS5 no-auth handshake.
  It distinguishes:
  - core not ready;
  - TCP port open but not a SOCKS5 listener;
  - local SOCKS ready.
- Added `--discord-proxy-route-plan`, a read-only explanation of the missing
  client-routing step with Flatpak/native/browser examples.
- `--discord-launch-through-socks` now accepts command strings such as:

```bash
PYTHONPATH=gui python -m zap2_gui.app --discord-launch-through-socks --discord-binary "flatpak run com.discordapp.Discord"
```

## GUI changes

The `Туннель` tab now has a `Маршрут через SOCKS` block:

- command field, defaulting to `flatpak run com.discordapp.Discord`;
- launch mode selector;
- route-plan button;
- launch-through-SOCKS button.

The launch composer plan now states explicitly that starting `tunnel-vless` only
starts a local SOCKS listener. It does not reroute already-open clients.

## Docs/tests

Updated tunnel, GUI shell, and roadmap docs. Added tests for Flatpak command-string
launching, route-plan text, SOCKS handshake probe text, GUI route controls, and
composer routing warnings.
