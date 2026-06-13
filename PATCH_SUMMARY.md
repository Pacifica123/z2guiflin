# Patch Summary — v0.4-alpha Stage 7n3

## v0.4-alpha Stage 7n3 — guided pre-TLS endpoint/counter correlation

This patch extends the Stage 7n2 guided Discord pre-TLS harness after the real-world run showed a valid `V3_NO_OUT_COUNTER_DELTA` report, while a later endpoint watch observed an `ESTAB` Discord socket and nft counters. The new goal is to avoid missing the actual updater-flow window.

### Added / changed

- The guided probe now runs a post-manual-action observation window before reading final counters.
- The observation window samples Discord endpoints through the existing read-only `ss`/`pgrep` endpoint watcher.
- Reports now include endpoint correlation:
  - endpoint snapshot path;
  - sample and observation counts;
  - socket states and ports;
  - capturePolicy match/miss counts;
  - ESTAB / SYN-SENT / ESTAB-with-SendQ counts;
  - primary endpoint summary.
- The endpoint watcher now filters out local zap2/nfqws2 diagnostic processes from the “Discord-like processes” list.
- `ss` parsing now preserves Recv-Q and Send-Q, so `ESTAB` with pending data can be separated from a clean TCP establishment.
- New verdicts:
  - `V3_NO_OUT_COUNTER_DELTA_WITH_ESTAB_ENDPOINT`;
  - `V8_TCP_ESTABLISHED`;
  - `V9_ESTAB_WITH_SENDQ`.
- `docs/DISCORD_PRETLS_GUIDED_PROBE.md` now documents Stage 7n3 endpoint/counter correlation.

### Not changed

- No new Discord bypass strategy.
- No broader capture policy by default.
- No automatic Discord launch.
- No hidden firewall/service mutation.
- No YouTube baseline changes.

### Validation

- Stage 7n2/7n3 guided probe tests.
- Discord endpoint discovery parsing tests.
- Runtime apply/session regressions.
- Strategy/workspace regressions.
- `compileall` for `gui` and `tests`.
