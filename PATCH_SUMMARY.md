# v0.4-alpha Stage 7e — Blockcheck Lab human tournament log and UI cleanup

This patch addresses the owner feedback that Blockcheck Lab still looked cramped and that Discord-like phase runs were hard to follow because the main screen streamed raw `blockcheck2.sh` output instead of explaining the GUI's own tournament state.

## Changed

- Phase-gated `ordered-target-chain` runs now show a human GUI tournament log in the main output area:
  - current phase and alternative;
  - when an AVAILABLE strategy is observed;
  - record-holder updates;
  - failed alternatives/phases;
  - manual stop or completed phase chain;
  - a short top-record list.
- Raw upstream blockcheck stdout/stderr are still written to `last-blockcheck.txt` and candidate logs; the button is renamed to `Raw log` to make that role explicit.
- The Blockcheck Lab form is less vertically cramped:
  - combo boxes and spin boxes get minimum heights;
  - action buttons get minimum heights/widths;
  - form columns get stable minimum widths;
  - the parameters group gets a safer minimum height.

## Not changed

- Stage 7e does not yet implement the full automatic one-strategy validator across every phase.
- It does not change runtime firewall/service behavior.
- Discord voice/UDP remains outside this non-voice loop.
