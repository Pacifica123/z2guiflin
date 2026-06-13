# v0.4-alpha Stage 7o0 — External working reference audit

## Summary

Stage 7o0 opens an external-reference lane for Discord/Linux work.  The patch does not add another bypass strategy; it imports a curated, read-only audit of provided working reference archives and exposes it through a CLI command.

## Added

- `references/external/stage7o0_external_reference_audit.json`
  - curated summaries of zapret2 Docker, Sergeydigl3 Linux, kartavkun Linux, Flowseal Windows, zapret2 Windows GUI, and upstream zapret2 core references;
  - capture envelopes, packet windows, hostlist/ipset shape, strategy families, risks, and future candidate families.
- `references/external/snippets/*.txt`
  - short non-runnable summaries of the reviewed external references.
- `docs/EXTERNAL_REFERENCE_AUDIT.md`
  - explains why Stage 7o0 exists, what was learned, and what must not be copied blindly.
- `gui/zap2_gui/adapters/external_reference_audit.py`
  - read-only loader and text renderer for the audit.
- CLI:
  - `PYTHONPATH=gui python -m zap2_gui.app --external-reference-audit`
- tests:
  - `tests/test_stage7o0_external_reference_audit.py`

## Safety boundary

- No third-party script is executed.
- No external archive is vendored wholesale into an executable workflow.
- No firewall/service mutation is added.
- No default strategy changes.
- Candidate families are named for future Stage 7o1 work but are not runnable strategies yet.

## Main finding

External working references generally combine broad capture envelopes with first-data/TLS/QUIC strategy families.  This suggests Zap2 should add a safe reference-inspired strategy lane instead of continuing only with narrow Discord edge-IP pre-TLS probes.
