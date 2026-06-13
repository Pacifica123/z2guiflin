# Discord observation matrix — Stage 7o2

Stage 7o2 adds a comparison layer for Discord experiments. It does not add a new bypass strategy and does not execute external scripts. Its purpose is to stop comparing Discord attempts from memory and to place each candidate into the same report shape.

The matrix rows are:

| Row | Purpose |
|---|---|
| `no zapret baseline` | Observe Discord with Zap2 runtime stopped. This separates app/network behavior from nfqws2 behavior. |
| `diagnostic pktdebug` | Validate the runtime observation funnel. |
| `current v2 strategy` | Re-test `community-discord-syndata-edge-flow-v2` under the same probe. |
| `kartavkun-like multisplit` | Observe the broad Linux-reference multisplit-like candidate. |
| `fake_tls_auto-like` | Observe the zapret2 generic TLS fake candidate. |
| `simple_fake-like` | Observe the Flowseal/simple-fake-like candidate. |

## Commands

Plan only:

```bash
PYTHONPATH=gui python -m zap2_gui.app --discord-observation-matrix-plan
```

Aggregate already collected evidence:

```bash
PYTHONPATH=gui python -m zap2_gui.app --discord-observation-matrix-report
```

The report is written to:

```text
.zap2/runtime/reports/discord-observation-matrix-*.json
.zap2/runtime/reports/discord-observation-matrix-*.md
```

## Owner loop for a strategy row

1. Close Discord fully.
2. Select the row strategy.
3. Start Default workflow through the existing owner-confirmed path.
4. Run the guided probe with `sudo` so nft counters can be read.
5. Open Discord only when the probe prints `MANUAL ACTION`.
6. Let the observation window complete.
7. Stop the workflow, then move to the next row.

## Interpretation rule

A candidate is not promoted because it exists in an external reference. A candidate can only be promoted if the matrix shows it changes a meaningful observation compared with the baseline and diagnostic rows: endpoint state, counter deltas, SYN+ACK visibility, Send-Q behavior, log/debug deltas, or Discord updater progress.

Stage 7o2 deliberately keeps the matrix as an observation tool. The first actual promotion of a candidate belongs to a later patch after evidence exists.
