# v0.4-alpha Stage 7o2a — matrix row runner

## Intent

Stage 7o2 introduced a Discord observation matrix, but collecting rows still required the owner to remember the full sequence: select strategy, start Default workflow, run guided probe with sudo, launch Discord only at the prompt, stop workflow, then move to the next row. This was too error-prone and repeatedly produced `V0_WORKFLOW_NOT_RUNNING` reports.

Stage 7o2a adds a state-aware row runner that simplifies one matrix row at a time without silently starting privileged firewall state.

## Changes

- Added CLI command:

```bash
PYTHONPATH=gui python -m zap2_gui.app --discord-observation-matrix-run-row <row-id>
```

- Added row aliases:
  - `baseline` -> `baseline-no-zapret`
  - `pktdebug` -> `diagnostic-pktdebug`
  - `v2` -> `current-v2-syndata`
  - `multisplit` -> `reference-kartavkun-multisplit`
  - `fake-tls` -> `reference-fake-tls-auto`
  - `simple-fake` -> `reference-simple-fake`
- Updated matrix plan commands to point to the row runner instead of raw low-level commands.
- Added `docs/DISCORD_OBSERVATION_MATRIX_ROW_RUNNER.md`.
- Added `references/external/snippets/stage7o2a-row-runner.txt`.
- Added tests for row-runner strategy selection/preparation and CLI exposure.

## Safety

The row runner does not:

- launch Discord;
- silently start/stop nft rules;
- auto-confirm privileged workflow plans;
- execute external scripts;
- write strategy selection as root.

It selects/prepares non-privileged state when safe, prints exact next owner-confirmed commands, and delegates to the existing guided probe only when the Default workflow is already running with the correct strategy.

## Checks

```bash
PYTHONPATH=gui pytest tests/test_stage7o2_observation_matrix.py -q
PYTHONPATH=gui pytest tests/test_stage7o1_external_reference_candidates.py tests/test_stage7o0_external_reference_audit.py tests/test_stage7n3_guided_pretls_endpoint_correlation.py -q
python -m compileall -q gui tests
```
