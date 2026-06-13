# v0.4-alpha Stage 7o2 — guided observation matrix

This patch adds a Discord observation matrix layer for comparing the no-zapret baseline, the diagnostic pre-TLS profile, the current v2 Zap2 candidate, and the external-reference candidates introduced in Stage 7o1.

It does not add a new bypass strategy and does not run external scripts. The goal is to aggregate generated guided probe reports and endpoint snapshots into one matrix before promoting any candidate.

## Added

- `gui/zap2_gui/adapters/discord_observation_matrix.py`
- CLI plan: `--discord-observation-matrix-plan`
- CLI report: `--discord-observation-matrix-report`
- `docs/DISCORD_OBSERVATION_MATRIX.md`
- `references/external/snippets/stage7o2-observation-matrix-plan.txt`
- tests for the Stage 7o2 matrix plan/report/CLI

## Safety

- read-only reporting only; no runtime start/stop; no Discord launch; no firewall/service mutation
- baseline row uses endpoint snapshots, strategy rows use already saved guided probe reports
- missing rows are explicit and do not masquerade as evidence

