# v0.4-alpha Stage 7p0 — Discord SOCKS/VLESS tunnel technical plan

Stage 7p0 opens a second Discord recovery lane next to the current `zapret2/nfqws2`
lane.  The current lane tries to keep Discord on the direct route and make the
first packets less recognizable.  The tunnel lane has a different philosophy:
route Discord through a local proxy/tunnel backend and stop treating every early
TLS packet as a desync puzzle.

This document is an implementation plan only.  It does not ship a VLESS client,
does not execute a tunnel, does not download external binaries, and does not
store the owner's private connection string in the repository.

## 1. Problem statement in plain terms

Current Discord observations show that the desktop client can reach TCP `ESTAB`
against Discord/Cloudflare endpoints, but still hangs on `Checking for updates`.
That means the blocker is no longer necessarily the first TCP knock; it can be
the first HTTPS/TLS/updater exchange after the door is already open.

The `zapret` lane is still valuable, but it is surgical: it must catch the right
packets at the right moment.  The tunnel lane is deliberately less surgical:
Discord traffic should leave through a known local proxy backend, so the direct
ISP-facing Discord path is not the only experiment.

## 2. Chosen architecture: orchestrate an external core, do not implement VLESS

Zap2GUIfLin should not implement the VLESS protocol itself in Python.  A correct
VLESS client quickly becomes a separate networking project: stream settings,
REALITY/TLS variants, routing, DNS, UDP, retries, logging, platform quirks, and
security-sensitive config handling.

The planned design is therefore:

```text
Zap2GUIfLin
  -> parses/imports connection profiles
  -> generates a local core config
  -> starts/stops an owner-selected external core binary
  -> exposes a local SOCKS listener on 127.0.0.1
  -> launches or guides Discord with proxy settings
  -> observes updater/app progress
```

The backend is an adapter, not a hard dependency.  The first practical targets
are external cores that already understand VLESS, such as `xray-core`,
`v2ray-core`, or `sing-box`.  Stage 7p0 does not choose one as mandatory; it
plans an adapter layer so the owner can point the app at an installed binary.

## 3. Why the v2rayNG reference is useful but must not be copied blindly

The uploaded `v2rayNG-2dust.zip` is an Android project.  It is still useful as a
reference because it demonstrates several concepts we need on Linux:

- share-link parsing for `vless://...` profiles;
- profile storage separate from the running core config;
- a local SOCKS inbound, commonly using a loopback port such as `10808`;
- optional UDP support on the SOCKS inbound;
- sniffing concepts for HTTP/TLS/QUIC;
- proxy-only service vs VPN/TUN service separation;
- per-app routing as a product concept.

Important boundary: v2rayNG is GPL-3.0 and Android/Kotlin-specific.  We should
use it as a conceptual reference and write a native Zap2GUIfLin implementation
from scratch unless the whole repository licensing story is explicitly changed.
No copied Kotlin code is planned for Stage 7p0.

## 4. The user-facing model

The existing app has strategy selection.  The tunnel lane adds connection
selection.

```text
Service target: discord-desktop
Runtime lane:
  - zapret direct strategy
  - SOCKS/VLESS tunnel

Tunnel connection:
  - imported VLESS URI profile A
  - imported VLESS URI profile B
  - custom core config profile

Discord launch mode:
  - observe only
  - launch via local SOCKS
  - updater-window via local SOCKS
  - future TUN/TProxy route
```

A connection profile is not a strategy.  A strategy describes how to desync or
capture traffic.  A connection profile describes where the tunnel goes.

## 5. VLESS URI import model

The owner may paste a connection string in the UI or pass it through a CLI import
command.  The parser must support a redacted/generic shape like this:

```text
vless://<uuid>@<server>:<port>?security=<mode>&encryption=none&type=tcp&host=<host>&headerType=http#<remarks>
```

The user's real value must never be committed into docs, tests, strategy files,
or patch summaries.  Runtime logs must redact secrets.

### 5.1 Parsed fields

The first parser should normalize these fields:

```text
scheme: vless
id: UUID/user id                       [secret]
server: hostname or IP                 [sensitive]
port: integer
remarks: decoded fragment label
query.encryption: usually none for VLESS
query.security: none | tls | reality | ...
query.type: tcp | ws | grpc | httpupgrade | ...
query.host: HTTP Host / transport host override
query.headerType: tcp header mode, for example http
query.sni: TLS SNI when present
query.alpn: ALPN list when present
query.flow: XTLS/REALITY flow when present
query.path: path for ws/grpc/httpupgrade when present
```

Stage 7p1 should implement a conservative parser that accepts known fields,
preserves unknown fields in a `rawQuery` map, and refuses malformed profiles
without network access.

### 5.2 Storage files

Connection profiles live under `.zap2`, not under versioned project data:

```text
.zap2/tunnel/connections/default.connections.json
.zap2/tunnel/default.active-connection.json
.zap2/tunnel/generated/default.core.json
.zap2/tunnel/logs/default.tunnel.jsonl
.zap2/tunnel/runtime/default.session.json
```

File permissions for secrets should be `0600` where the platform allows it.
Redacted metadata can be printed to normal logs; raw connection strings cannot.

## 6. Local SOCKS mode

The first runnable tunnel mode should be `proxy-only SOCKS`:

```text
external core outbound: selected VLESS profile
local inbound: socks://127.0.0.1:<port>
local bind: loopback only
socks auth: noauth for loopback-only MVP
udp: initially off unless explicitly enabled
```

Why SOCKS first:

- it can be tested without kernel routing changes;
- it does not require nftables or NFQUEUE;
- it has a small rollback surface: stop the core process;
- it lets us test Discord updater behavior before building TUN/TProxy.

Main limitation: desktop Discord may not route every network path through
standard proxy environment variables.  That is an experiment, not an assumption.

## 7. Discord launch modes

### 7.1 Observe-only

No proxy.  This is the current baseline idea: launch Discord manually and record
endpoint/process state.

### 7.2 Launch via local SOCKS

Zap2GUIfLin starts the core, then launches Discord with a controlled environment
and/or Electron/Chromium proxy flag candidates:

```text
ALL_PROXY=socks5://127.0.0.1:<port>
HTTPS_PROXY=socks5://127.0.0.1:<port>
HTTP_PROXY=socks5://127.0.0.1:<port>
--proxy-server=socks5://127.0.0.1:<port>
```

The implementation must treat these as candidates.  It must measure whether
Discord actually uses the local SOCKS port instead of assuming success.

### 7.3 Updater-window via local SOCKS

The original idea was “proxy only the update check, then restart normal”.  That
is probably too brittle because Discord checks updates on every launch.  The
safer interpretation is:

```text
Start Discord once through the proxy.
Keep the proxy active through the updater phase.
If the app reaches the main window, either keep using the proxy for this process
or let the owner manually stop and compare behavior.
Do not auto-restart Discord into direct mode as the default.
```

This keeps the user idea, but avoids the broken assumption that a relaunch will
skip the updater.

### 7.4 Future TUN/TProxy route

If SOCKS launch mode fails because Discord ignores the proxy or only partially
uses it, the next lane is system-level routing:

```text
Discord domains/IPs -> tunnel backend
other traffic       -> direct
```

That likely needs root, DNS control, nftables, and a stronger rollback contract.
It is explicitly not Stage 7p1.

## 8. Runtime state machine

The tunnel runner should be boring and explicit:

```text
NO_CONNECTION_SELECTED
  -> CONNECTION_SELECTED
  -> CORE_BINARY_FOUND
  -> CORE_CONFIG_PREPARED
  -> OWNER_CONFIRMED_START
  -> CORE_RUNNING
  -> DISCORD_LAUNCH_PREPARED
  -> DISCORD_STARTED_BY_OWNER_OR_WRAPPER
  -> UPDATER_OBSERVED
  -> RESULT_AVAILABLE
  -> STOPPED
```

The app should not hide state transitions behind a single magic button until the
owner can inspect the generated config and rollback notes.

## 9. CLI plan

Stage 7p1+ should add commands shaped like this:

```bash
PYTHONPATH=gui python -m zap2_gui.app --tunnel-connection-import-vless @/path/to/link.txt
PYTHONPATH=gui python -m zap2_gui.app --tunnel-connections
PYTHONPATH=gui python -m zap2_gui.app --tunnel-select-connection <connection-id>
PYTHONPATH=gui python -m zap2_gui.app --discord-tunnel-plan
PYTHONPATH=gui python -m zap2_gui.app --runtime-confirm <plan-id>
PYTHONPATH=gui python -m zap2_gui.app --discord-tunnel-start --confirm <plan-id>
PYTHONPATH=gui python -m zap2_gui.app --discord-launch-through-socks
PYTHONPATH=gui python -m zap2_gui.app --discord-tunnel-probe
PYTHONPATH=gui python -m zap2_gui.app --discord-tunnel-stop
```

After the workflow is proven, a single guided command can be added, similar to
`--matrix-row-auto`:

```bash
PYTHONPATH=gui python -m zap2_gui.app --discord-tunnel-run --mode socks-updater-window
```

But the first implementation should keep plan/confirm boundaries visible.

## 10. GUI plan

The GUI should add a tunnel section without replacing existing strategy UI:

```text
Discord target card
  Direct strategy lane
    selected zapret strategy
    matrix/probe status
  Tunnel lane
    selected connection profile
    core backend path/status
    local SOCKS address
    launch mode
    Start tunnel
    Launch Discord through tunnel
    Probe updater
    Stop tunnel
```

Connection strings are pasted through a modal that immediately shows a redacted
preview:

```text
protocol: VLESS
destination: <redacted-host>:8080
transport: tcp/http-header
security: none
local mode: SOCKS 127.0.0.1:<auto>
remarks: <decoded label>
```

## 11. Core config generation

The generated core config should be minimal and auditable:

```text
inbounds:
  - socks loopback inbound
outbounds:
  - selected VLESS outbound
  - direct fallback only if needed for DNS or core health probes
routing:
  - default to proxy for the local SOCKS inbound
log:
  - warning/info, no secrets
```

The generator should support at least these profile variants:

```text
vless-tcp-none-http-header
vless-tcp-tls
vless-ws-tls
vless-reality-tcp       [later]
custom-json             [manual expert import, not default]
```

The first runnable target can support only the subset needed by the owner's
example: TCP transport, `encryption=none`, `security=none`, optional HTTP header
host/headerType.

## 12. Probes and success criteria

The tunnel lane must produce evidence just like the zapret matrix.

### 12.1 Core probe

Before launching Discord:

```text
core process running: yes/no
local socks port open: yes/no
outbound config redacted hash: <hash>
```

### 12.2 SOCKS path probe

Use a harmless HTTPS probe through the local SOCKS listener to prove the local
proxy path works.  The target URL should be configurable; it should not be a
Discord-only hard-coded assumption.

### 12.3 Discord updater probe

Compare these observations:

```text
Discord launched by Zap2 wrapper: yes/no
Discord process env/proxy flags applied: yes/no
connections to local socks port observed: yes/no
connections direct to Discord endpoints observed: yes/no
updater still stuck: yes/no/unknown
main window reached: yes/no/unknown
```

### 12.4 Success levels

```text
T0_CORE_ONLY        core starts and SOCKS opens
T1_PROXY_WORKS      non-Discord probe succeeds through SOCKS
T2_DISCORD_USES     Discord connects to local SOCKS
T3_UPDATER_PASSES   updater window passes while tunnel is active
T4_APP_USABLE       gateway/API/media baseline works enough for non-voice use
```

## 13. Safety and rollback

The tunnel lane must preserve the existing safety style:

- no automatic external downloads;
- no execution of uploaded third-party scripts;
- owner supplies or selects the external core binary;
- all generated configs are inspectable before start;
- start requires owner confirmation;
- local SOCKS binds to `127.0.0.1` only;
- secrets are stored under `.zap2` with restrictive permissions;
- secrets are redacted in logs, reports, docs, and patch summaries;
- stop kills only the managed core process recorded in the Zap2 session file;
- TUN/TProxy is a later root-required mode, not part of SOCKS MVP.

## 14. Interaction with existing zapret runtime

The initial tunnel runner should refuse to start if the Default zapret workflow
is active, unless the owner explicitly selects an advanced mixed mode.  Mixing
NFQUEUE desync and proxy routing during the first experiments will make evidence
harder to interpret.

Planned rule:

```text
zapret workflow running + tunnel start requested -> stop and explain
```

Future expert mode can allow both, but only with evidence labels showing which
lane was active.

## 15. Implementation stages

### Stage 7p0 — this plan

Add the technical plan, v2rayNG reference notes, safety rules, and tests that
prevent committing the real connection string.

### Stage 7p1 — connection profile model and parser

Implement a pure, no-network parser for VLESS URIs and profile storage under
`.zap2/tunnel`.  Add redaction and round-trip tests.  No core execution yet.

### Stage 7p2 — external core inventory and config generator

Add backend inventory:

```text
xray-core path candidate
v2ray-core path candidate
sing-box path candidate
custom path
```

Generate redacted local SOCKS configs but do not start the core by default.

### Stage 7p3 — owner-confirmed core start/stop

Add plan/confirm/start/stop for the external core in proxy-only mode.  Record
PID, config hash, local port, stdout/stderr log paths.

### Stage 7p4 — Discord SOCKS launch wrapper

Add a launcher that starts Discord with proxy env/flags, records process ID, and
samples whether it connects to the local SOCKS port.

### Stage 7p5 — updater-window experiment

Add a guided runner:

```text
start core -> launch Discord through SOCKS -> observe updater -> report verdict
```

Do not auto-restart Discord into direct mode.

### Stage 7p6 — GUI integration

Add connection selector, redacted profile preview, tunnel status card, and safe
buttons.

### Stage 7p7 — optional TUN/TProxy research plan

Only if SOCKS cannot make Discord use the tunnel reliably.

## 16. Open questions for the owner experiments

The first implementation should answer these, not guess them:

```text
Does Linux desktop Discord honor proxy env vars?
Does Electron/Discord honor --proxy-server when launched externally?
Does the updater use the same process and proxy settings as the main app?
Does gateway/API traffic continue through SOCKS after updater passes?
Is UDP/voice needed for the v0.4 success definition, or deferred?
Which external core is already installed or acceptable to install manually?
```

## 17. Definition of done for the first useful tunnel MVP

The SOCKS/VLESS lane becomes useful when the app can do this safely:

```text
1. import a VLESS URI without leaking it;
2. select it as the active Discord tunnel connection;
3. generate a redacted local SOCKS core config;
4. start the external core through owner-confirmed runtime flow;
5. launch Discord through the local SOCKS candidate mode;
6. prove whether Discord actually uses the local SOCKS port;
7. report whether updater passes;
8. stop the managed core cleanly.
```

That MVP is enough to decide whether the new philosophy is worth promoting from
experiment to real runtime backend.


## 18. Stage 7p1-7p4 implementation status

Stage 7p1 through the first practical part of Stage 7p4 are now implemented as
CLI/runtime primitives.  This is still an experimental lane, but it is no longer
documentation-only.

Implemented pieces:

```text
connection import     -> --tunnel-connection-import-vless URI_OR_@FILE
connection list       -> --tunnel-connections
connection select     -> --tunnel-select-connection CONNECTION_ID
core config plan      -> --discord-tunnel-plan [--tunnel-core-binary PATH]
owner confirmation    -> --runtime-confirm PLAN_ID
core start            -> --discord-tunnel-start --confirm PLAN_ID
core status/probe     -> --discord-tunnel-status / --discord-tunnel-probe
core stop             -> --discord-tunnel-stop
Discord SOCKS launch  -> --discord-launch-through-socks
```

The implementation keeps these safety constraints from the plan:

- no external core is downloaded automatically;
- the owner supplies or installs `xray`, `v2ray`, or `sing-box`;
- generated core config is written under `.zap2/tunnel/generated` with restrictive
  permissions;
- raw VLESS UUID/server values are stored only in `.zap2/tunnel`, not in project
  files, docs, or normal CLI output;
- the start plan goes through the same `--runtime-confirm` confirmation gate used
  elsewhere in the project;
- SOCKS binds to `127.0.0.1`;
- the tunnel start path refuses to mix with an already-running default zapret
  workflow;
- stop kills only the PID recorded in `.zap2/tunnel/runtime/default.session.json`.

Current limitations:

- the first config generator targets VLESS over TCP with `security=none` and
  `headerType=http`, plus basic TLS/WS shaping hooks;
- SOCKS path probing only confirms core/process/loopback port readiness; it does
  not yet perform a full HTTPS request through SOCKS;
- Discord updater success is still manual observation after
  `--discord-launch-through-socks`;
- GUI controls are not implemented yet;
- TUN/TProxy remains a later research lane.
