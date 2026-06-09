# v0.4-alpha Stage 7c — phase-gated tournament runner correction

This patch fixes the Stage 7b owner-observed mismatch where the Blockcheck GUI still scanned later raw targets after earlier required Discord phases were blocked.

## Changed

- The Blockcheck Lab runner now enables a phase-gated mode for presets whose service coverage policy is `ordered-target-chain`.
- For phase-gated runs, phases are processed in policy order and targets inside a phase are alternatives.
- A phase must have an AVAILABLE alternative before the runner may advance to the next phase.
- If a required phase has no AVAILABLE alternative after all its targets are tried, the runner stops before later phases.
- If a phase alternative becomes AVAILABLE, the GUI stops that candidate and advances to the next phase instead of spending hundreds of checks on the same target.
- Footer wording now says `auto stopped candidate` rather than `auto skipped dead target`, because Stage 7c uses auto-stop both for dead targets and for enough evidence on a passed phase.
- Tests document that the GUI runner is phase-gated and no longer just a raw coverage scan for ordered desktop-style services.

## Not changed

- YouTube remains `any-target-available`.
- Discord voice/UDP remains reserved for the later voice stage.
- Stage 7c does not yet implement the full automatic record-holder strategy validator across upstream custom one-strategy lists; it fixes the live GUI ordering/phase gate first.
