# v0.4-alpha Stage 7o1 — External-inspired candidate strategies

## Purpose

Stage 7o1 turns the Stage 7o0 audit into owner-selectable Zap2 strategies. It does **not** change the default strategy, does not run third-party scripts, and does not claim Discord support is fixed.

The goal is to test external working-reference ideas under Zap2's owner-confirmed runtime and guided observation harness:

```text
external capture/profile model
→ safe Zap2 candidate strategy
→ owner-selected observation
→ Stage 7o2 matrix
→ promote only if it changes Discord updater behavior
```

## Added candidates

### `reference-zapret2-generic-tls-fake`

Source basis: upstream/vernette zapret2 examples.

Shape:

```text
TCP: 80,443
HTTP: http_methodeol
TLS: fake_default_tls with tcp_ts
UDP: off in Stage 7o1
```

This candidate is meant for the newer observation that Discord can reach `ESTAB` but still spin on the updater. It targets first TLS payload rather than SYN-only behavior.

### `reference-linux-general-multisplit-like`

Source basis: kartavkun general configs plus zapret2-compatible multisplit/multidisorder primitives.

Shape:

```text
TCP capture: 80,443,2053,2083,2087,2096,8443
Host bucket: profiles/hostlists/reference-general.hosts
HTTP: fake + multisplit
TLS: fake + multidisorder
UDP: off in Stage 7o1
```

This is the broad general-bucket candidate closest to the “working Linux config pack” shape, but still owner-scoped and non-default.

### `reference-flowseal-simple-fake-like`

Source basis: Flowseal/Sergeydigl3 simple fake TCP branches.

Shape:

```text
TCP capture: 80,443,2053,2083,2087,2096,8443
Discord media high TLS ports: TCP simple fake
General host bucket: TCP simple fake
UDP/STUN/game-filter: deferred
```

This is a TCP-only translation of the broad Flowseal-like fake family. It intentionally omits UDP/voice and service installation.

## Shared safety boundary

All three candidates:

```text
- are owner-selectable only;
- are not default;
- are still plan-only in checks;
- use owner UID scoped nft/NFQUEUE capture;
- do not import external installers;
- do not enable service mode;
- leave UDP/voice for a later explicit lane;
- are intended for Stage 7o2 observation matrix.
```

## How to test one candidate manually

Choose exactly one candidate:

```bash
PYTHONPATH=gui python -m zap2_gui.app --select-strategy reference-linux-general-multisplit-like
```

Then use the normal owner-confirmed build/start workflow. After runtime is running, use the guided probe:

```bash
sudo env PYTHONPATH=gui python -m zap2_gui.app --runtime-discord-pretls-guided-probe
```

The result must be interpreted as an observation report, not as a success/failure slogan.

## What Stage 7o1 does not solve

Stage 7o1 does not yet provide the full matrix runner. It only makes the candidates selectable. The next stage should compare:

```text
no zapret baseline
community-discord-pretls-diagnostic-pktdebug
community-discord-syndata-edge-flow-v2
reference-zapret2-generic-tls-fake
reference-linux-general-multisplit-like
reference-flowseal-simple-fake-like
```

using the same endpoint/counter/session evidence format.
