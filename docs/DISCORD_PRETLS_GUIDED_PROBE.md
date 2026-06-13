# Discord pre-TLS guided probe harness

Stage `v0.4-alpha_stage7n2` turns the Stage 7n/7n1 observability pieces into one owner-facing diagnostic run.

The purpose is not to fix Discord and not to add another imported preset. The purpose is to reduce one unknown at a time:

```text
Discord SYN
→ nft counter
→ live nfqws2 PID
→ NFQUEUE/session consistency
→ log/debug delta
→ verdict
→ next allowed branch
```

## Command

```bash
PYTHONPATH=gui python -m zap2_gui.app --runtime-discord-pretls-guided-probe
```

The command is read-only with respect to firewall and services. It writes only report files under:

```text
.zap2/runtime/reports/
```

For CI/dry-run state checks without waiting for a manual Discord launch:

```bash
PYTHONPATH=gui python -m zap2_gui.app --runtime-discord-pretls-guided-probe --pretls-probe-no-wait
```

## Required state

Before running the guided probe for a real Discord attempt:

```text
1. Select community-discord-pretls-diagnostic-pktdebug.
2. Start the Default workflow through the existing owner-confirmed path.
3. Confirm that the workflow is running.
4. Run the guided probe.
5. Only when the probe prints MANUAL ACTION, open Discord from the desktop/menu.
```

The command must not silently start or stop the runtime. If the workflow is not running, it returns a verdict telling the owner to start it first.

## UX rule

The probe output must clearly separate:

```text
SHELL COMMAND — can be copied into a terminal.
MANUAL ACTION — human action; do not type into shell.
INTERPRETATION — what the result means.
NEXT BRANCH — what kind of patch is allowed next.
```

This exists because Stage 7n1 revealed that a line like `launch Discord until Checking for updates` can be misread as a shell command. In this project, that is a diagnostic-validity problem, not a cosmetic issue.

## Report fields

The generated JSON/Markdown report includes:

```text
profile
selected strategy
active/applied strategy
strategy mismatch / compatibility
workflow state
nft table
qnum from snapshot
qnum from session record
nfqws2 PID before/after
nft tcp-out counter before/after/delta
nft tcp-in-synack counter before/after/delta
nft tcp-in-fin-rst counter before/after/delta
stdout/stderr/debug size before/after/delta
args file path and hash
verdict
next branch
```

## Verdicts

```text
V0_WORKFLOW_NOT_RUNNING
  Runtime owner-rules are not applied. Start Default workflow first.

V0_STRATEGY_NOT_PRETLS_DIAGNOSTIC
  Active strategy is not the Discord pre-TLS diagnostic profile/capturePolicy.

V1_NFT_TABLE_MISSING
  Workflow state says rules should be present, but the nft table is missing/unreadable.

V1_NFT_COUNTER_READ_FAILED
  nft counters could not be read. Run with sufficient privileges for read-only nft inspection or attach manual output.

V2_NFQWS2_DEAD_BEFORE
  nfqws2 is not alive before the Discord manual action.

V2_QNUM_MISMATCH
  nft queue number and session queue number differ.

V3_NO_OUT_COUNTER_DELTA
  Discord launch did not increase the outbound pre-TLS nft counter in this run.

V4_NFQWS2_DIED_AFTER_HIT
  nft outbound counter increased, but nfqws2 was not alive after the manual action.

V5_OUT_HIT_ALIVE_LOGS_SILENT
  nft outbound counter increased and nfqws2 stayed alive, but logs/debug did not change.

V6_LOG_ACTIVITY_WITH_OUT_HIT
  nft outbound counter increased, nfqws2 stayed alive, and logs/debug changed.

V7_SYNACK_SEEN
  inbound SYN+ACK diagnostic counter increased; move to socket/TLS/updater-stage analysis.
```

## What this patch intentionally does not do

```text
It does not add a new Discord bypass strategy.
It does not broaden capture globally.
It does not start Discord by itself.
It does not apply nft rules or ask for sudo by itself.
It does not treat the report as success unless the verdict changes the next allowed branch.
```

The next patch after Stage 7n2 must be chosen from the generated verdict, not from a new imported preset by default.
