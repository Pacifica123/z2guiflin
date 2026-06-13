# v0.4-alpha Stage 7o0 — External working reference audit

## Purpose

Stage 7o0 opens a new external-reference lane after the Stage 7n diagnostics showed that Zap2 was becoming too narrow: the project was looking mostly at Discord-specific pre-TLS/SYN capture while external working Linux/Windows references generally use broader capture envelopes and first-data/TLS strategy families.

This stage is deliberately **reference-only**. It does not run third-party scripts, does not install services, does not change the default strategy, and does not mutate firewall rules.

## Imported reference material

The curated audit is stored in:

```text
references/external/stage7o0_external_reference_audit.json
```

Short non-runnable snippets are stored in:

```text
references/external/snippets/
```

The audit summarizes these provided archives:

```text
zapret2-vernette-docker-master.zip
zapret-Sergeydigl3-linux-Stable4.zip
zapret-Sergeydigl3-linux-master.zip
zapret-kartabkun-linux-main.zip
zapret1-flowseal-windows.zip
zapret2-gui_windows.zip
zapret2-core-from_bolvan.zip
```

## Main findings

External references are not mainly “one more Discord hostname list”. They combine two layers:

```text
capture envelope
→ strategy/profile family
```

The capture envelope is usually broader than our Stage 7n diagnostic profile:

```text
TCP: often 80,443 plus 2053,2083,2087,2096,8443 and sometimes game-filter ranges
UDP: often 443 plus Discord/STUN/game/media ranges
packet windows: often wider than first 1-8 packets; zapret2 examples use 20 out / 10 in for TCP
scope: usually not Discord-edge-IP-only and not owner-UID-only
```

The strategy/profile layer often targets first established payload/TLS/QUIC rather than only SYN:

```text
fake TLS
multisplit / multidisorder
fake QUIC
hostlist list-general / ipset-all
Discord media / STUN branches
Windows-only WinDivert raw-part envelopes
```

This matches the latest Zap2 observation: Discord can reach `ESTAB` with `Send-Q > 0` and still spin on `Checking for updates`, so the problem may sit at:

```text
TCP established → first payload / TLS / updater HTTPS exchange
```

rather than only at:

```text
SYN → SYN+ACK
```

## CLI

Show the reference audit without executing anything:

```bash
PYTHONPATH=gui python -m zap2_gui.app --external-reference-audit
```

The command is read-only and prints:

```text
sources
capture ports
packet windows
strategy families
cross-source findings
future candidate families
recommended next stages
```

## Safety boundary

Stage 7o0 intentionally refuses these shortcuts:

```text
run external scripts directly
copy service installers into Zap2 workflow
import broad firewall rules as defaults
silently broaden capture for all users
turn Windows WinDivert flags into Linux nft rules without translation
switch from diagnostics to bypass without observation matrix
```

## Candidate families for future Stage 7o1

The audit defines candidate families, but they are **not runnable strategies yet**:

```text
reference-zapret2-generic-tls-fake
reference-linux-general-multisplit-like
reference-flowseal-simple-fake-like
reference-discord-urgent-sni-later
```

They are deliberately staged for a future patch because each needs:

```text
owner-confirmed capturePolicy
safe preview
YouTube regression protection
guided observation matrix
nfqws2/Lua primitive compatibility proof
```

## Recommended next stages

```text
Stage 7o1:
  create safe external-inspired candidate strategies without changing defaults.

Stage 7o2:
  run observation matrix across no-zapret baseline, diagnostic pktdebug, current v2, and reference-inspired candidates.

Stage 7o3:
  promote only the candidate that changes Discord updater behavior under observation.
```

## Why this stage exists

The project should stop treating every Discord failure as evidence that we need another Discord domain or another pre-TLS probe. Stage 7o0 gives the next patches a wider reference basis:

```text
not “copy working scripts”
but “extract their capture/profile model safely and test it under Zap2 observation”.
```
