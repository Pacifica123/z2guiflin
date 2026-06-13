# Patch Summary — v0.4-alpha Stage 7n2

## v0.4-alpha Stage 7n2 — guided Discord pre-TLS probe harness

This patch adds an owner-facing guided diagnostic harness for the Discord Linux pre-TLS/SYN-SENT problem.

### Added

- `--runtime-discord-pretls-guided-probe` CLI action.
- `--pretls-probe-no-wait` and `--pretls-probe-wait-seconds` options for CI/dry-run use.
- `.zap2/runtime/reports/discord-pretls-guided-probe-*.json` and `.md` report generation.
- Verdict engine for workflow/nft/nfqws2/counter/log states.
- Clear separation of `SHELL COMMAND` and `MANUAL ACTION` prompts.
- `docs/DISCORD_PRETLS_GUIDED_PROBE.md`.

### Not changed

- No new Discord bypass strategy.
- No silent firewall/service mutation.
- No automatic Discord launch.
- No YouTube baseline changes.

### Validation

- Stage 7n2 guided probe tests.
- Stage 7n/7n1 observability regressions.
- Runtime apply/session regressions.
- Stage 7j/7k/7l/7m strategy regressions.
- `compileall` for `gui` and `tests`.
