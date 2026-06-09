# v0.4-alpha Stage 7d — Discord precheck guard and Blockcheck Lab UX cleanup

This patch responds to the owner-observed Stage 7c run where `stable.dl2.discordapp.net` was marked `dead-target` from a single failed TCP/443 port precheck even though earlier runs had produced many AVAILABLE strategies for the same target.

## Changed

- `BlockcheckOptions` now carries a `dead_target_guard` mode:
  - `auto-stop` keeps the old evidence-based early stop behavior;
  - `observe-only` keeps port-precheck evidence in logs/statistics but does not terminate the candidate before strategy scan.
- GUI Discord desktop preset now defaults `Auto-skip dead target` to off (`observe-only`) because ordered Discord updater/CDN phases can produce false dead-target evidence from transient/resolved IP behavior.
- CLI `--blockcheck-plan/--blockcheck-run --blockcheck-target-preset discord-desktop` now also defaults to `observe-only`; owners can force the old behavior with `--blockcheck-dead-target-guard auto-stop`.
- Blockcheck Lab controls are made less cramped:
  - default window size is increased to 1040x720 with bounded minimum size;
  - action buttons are split into two rows inside an Actions box;
  - long labels are shortened;
  - the dead-target guard is visible as an explicit checkbox.
- Added `docs/DISCORD_FLOWSEAL_WINDOWS_REFERENCE.md` with non-executable research notes from Flowseal/Windows presets.

## Not changed

- Stage 7d does not implement the full automatic record-holder validator that takes one strategy and proves it across every phase.
- Flowseal/Windows `winws.exe`, WinDivert, `--wf-*` and `--dpi-desync-*` arguments are not executed on Linux.
- Discord voice/UDP remains reserved for the later voice stage.
