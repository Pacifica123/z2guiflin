# Discord observation matrix row runner

Stage 7o2a adds a small UX layer above the Stage 7o2 matrix. The previous matrix plan was correct but too easy to misuse: it printed a guided-probe command even when the Default workflow was not running, so the owner could repeatedly hit `V0_WORKFLOW_NOT_RUNNING`.

The new row runner is still conservative: it does not silently start privileged firewall state, does not launch Discord, and does not bypass owner confirmation. It only reduces the number of states the owner has to remember.

## Command

```bash
PYTHONPATH=gui python -m zap2_gui.app --discord-observation-matrix-run-row <row-id>
```

Supported row ids are the same ids shown by:

```bash
PYTHONPATH=gui python -m zap2_gui.app --discord-observation-matrix-plan
```

Useful aliases are accepted for common rows:

```text
baseline -> baseline-no-zapret
pktdebug -> diagnostic-pktdebug
v2 -> current-v2-syndata
multisplit -> reference-kartavkun-multisplit
fake-tls -> reference-fake-tls-auto
simple-fake -> reference-simple-fake
```

## Baseline row

For `baseline-no-zapret`, the runner refuses to continue if the Zap2 Default workflow appears to be running, because the baseline must be collected without the Zap2 runtime. If the runtime is stopped, the runner asks the owner to close Discord, then opens a read-only endpoint watch window and asks the owner to launch Discord manually.

The baseline runner still does not start Discord itself.

## Strategy rows

For strategy rows, the runner does three state-aware things:

1. If run as the normal owner user and the row strategy is not selected, it selects that strategy.
2. If the Default workflow is not running, it prepares the start plan and prints the exact next shell commands: confirm plan, sudo start, then rerun the same row runner.
3. If the Default workflow is running with the correct strategy, but the process is not root, it prints the exact sudo row-runner command needed for read-only nft counter inspection.

Only when the Default workflow is already running with the correct strategy and the row runner is executed with enough privileges for nft counter reads will it delegate to the existing guided pre-TLS probe.

## Why root selection is refused

The command refuses to write `.zap2` strategy selection as root. This avoids root-owned project state created by accidental `sudo` use. The intended pattern is:

```bash
PYTHONPATH=gui python -m zap2_gui.app --discord-observation-matrix-run-row diagnostic-pktdebug
# follow the printed owner-confirmed start commands
sudo env PYTHONPATH=gui python -m zap2_gui.app --discord-observation-matrix-run-row diagnostic-pktdebug
```

## What this patch does not do

It does not:

- add a new bypass strategy;
- execute external scripts;
- install services;
- silently start or stop nft rules;
- launch Discord automatically;
- mark any reference candidate as a final Discord solution.

It only turns the matrix row collection loop into a state-aware guided runner so the owner no longer has to remember the full workflow from previous messages.


## Stage 7o2b baseline runner fix

The baseline row runner now calls the endpoint watcher through its keyword-only API (`root=...`, `seconds=...`). This fixes the baseline crash where `run_discord_endpoint_watch()` was called with positional arguments and failed before the 45 second watch window could start.

## Stage 7o2c build-aware row runner

The row runner now also handles the missing `nfqws2` binary state before it prepares a runtime start plan. If the binary is absent or not executable, it prepares the correct build plan for the currently selected row strategy and prints the exact owner-side commands:

```bash
PYTHONPATH=gui python -m zap2_gui.app --runtime-confirm <build-plan-id>
PYTHONPATH=gui python -m zap2_gui.app --default-build --confirm <build-plan-id>
PYTHONPATH=gui python -m zap2_gui.app --discord-observation-matrix-run-row <row-id>
```

This prevents the old confusing path where `--default-start` failed with a stale `manual-local` build-plan hint. Local build remains owner-confirmed and non-root; the runner still does not silently start firewall state, launch Discord, or execute external scripts.


## Stage 7o2d auto mode

Use `--matrix-row-auto` to collapse the owner-side build/confirm/start-plan preparation into one command and the privileged start+probe into one sudo rerun. Discord must still be opened only after the probe prints `MANUAL ACTION`.
