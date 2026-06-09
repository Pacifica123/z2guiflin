# Discord endpoint discovery — v0.4-alpha Stage 7g

Stage 7g adds a read-only diagnostic layer for the current Discord desktop blocker: the splash screen can stay on `Checking for updates` even when guessed updater domains fail or return mixed Blockcheck evidence.

The goal is to stop guessing the updater path and collect local evidence from the running desktop process first.

## What this diagnostic does

The endpoint watch samples local `ss -tunp` and `pgrep -af [Dd]iscord` output for a short owner-controlled window. It records process-owned TCP/UDP sockets that are visible to the current user while Discord is on the updater splash.

It does not:

- launch Discord;
- request sudo;
- mutate firewall, nftables, systemd, hostlists or runtime state;
- capture packet payloads;
- store credentials;
- prove that a zapret strategy works.

Saved snapshots live under:

```text
.zap2/discord-discovery/
```

## CLI loop

```bash
PYTHONPATH=gui python -m zap2_gui.app --discord-endpoint-plan
PYTHONPATH=gui python -m zap2_gui.app --discord-endpoint-watch --discord-endpoint-seconds 90
PYTHONPATH=gui python -m zap2_gui.app --discord-endpoint-report
```

During `--discord-endpoint-watch`, start Discord and leave it on `Checking for updates`.

## GUI loop

Open `Диагностика → Blockcheck lab` and press `Endpoints`. The button prints the plan plus the latest saved report. The long-running watch itself is intentionally CLI-first so the GUI does not freeze while the owner starts/stops Discord manually.

## How to interpret results

- TCP/443 endpoints are candidates for updater/app/CDN target registry review.
- Non-443 TCP endpoints may explain why `discord.media` has separate Windows/Flowseal rules on 2053/2083/2087/2096/8443.
- UDP endpoints during the updater splash would be evidence that the current failure path is not purely TCP/TLS; that would justify opening a pre-voice UDP investigation before the reserved voice stage.
- No observed endpoints means the owner should run a longer watch, verify process names, or use an external privileged packet capture manually.

## Why this is not another Blockcheck target guess

Previous Stage 7 patches guessed `updates.discord.com` and `stable.dl2.discordapp.net` as updater alternatives. That is still useful evidence, but it is not enough. The updater splash belongs to the actual Electron/Discord process, so Stage 7g adds a way to see what that process touches locally before the registry/tournament is changed again.
