# v0.4-alpha Stage 7o2d — auto observation matrix row runner

Stage 7o2d reduces the row-runner workflow from a plan-id maze to a two-phase
owner/sudo flow.

## Changed

- `--discord-observation-matrix-run-row <row> --matrix-row-auto` added.
- Owner phase now:
  - selects the row strategy;
  - builds `nfqws2` automatically if the executable is missing;
  - prepares and confirms the default start workflow plan;
  - prints one sudo command for the privileged phase.
- Sudo phase now:
  - starts Default workflow for the selected row if needed;
  - then enters the existing guided Discord pre-TLS probe;
  - asks the owner to open Discord only at `MANUAL ACTION`.
- Existing non-auto mode is kept for conservative/manual operation.
- Added docs/snippet for the auto row-runner mode.

## Safety

- Does not launch Discord automatically.
- Local build runs as the owner, not root.
- Firewall/NFQUEUE changes only happen in the explicit sudo phase.
- No external scripts are executed.
- Matrix reports remain the source of truth for comparing candidates.
