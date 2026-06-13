# v0.4-alpha Stage 7o1 — External-inspired candidate strategies

## Summary

Stage 7o1 turns the Stage 7o0 reference audit into owner-selectable Zap2 candidate strategies.  It does not change the default strategy, does not execute third-party scripts, and does not claim Discord is fixed.  The new lane exists so Stage 7o2 can compare real external-inspired candidates under the same guided Discord observation harness.

## Added

- `strategies/reference-zapret2-generic-tls-fake.json`
  - zapret2/nfqws2-compatible generic HTTP/TLS first-data candidate based on upstream/vernette patterns;
  - TCP 80/443, no UDP in Stage 7o1.
- `strategies/reference-linux-general-multisplit-like.json`
  - broad general Discord/Cloudflare bucket candidate inspired by kartavkun/general + zapret2 multisplit/multidisorder primitives;
  - TCP 80/443 plus 2053/2083/2087/2096/8443, no UDP in Stage 7o1.
- `strategies/reference-flowseal-simple-fake-like.json`
  - TCP-only Flowseal/Sergeydigl3 simple-fake-like candidate;
  - broad owner-scoped TCP capture and repeated fake TLS/HTTP profiles, while UDP/STUN/game-filter is deferred.
- `profiles/hostlists/reference-general.hosts`
  - curated host bucket from external references: Discord, Cloudflare/ECH/CDN, YouTube baseline and adjacent media hosts.
- `docs/EXTERNAL_REFERENCE_CANDIDATE_STRATEGIES.md`
  - explains the candidate lane, safety boundaries, and how to test one candidate under the guided probe.
- `references/external/snippets/stage7o1-candidate-strategies-summary.txt`
  - non-runnable summary of the three candidates.
- tests:
  - `tests/test_stage7o1_external_reference_candidates.py`

## Changed

- `strategies/catalog.json`
  - registers the three Stage 7o1 candidate strategies while keeping `manual-local` as default.
- `docs/EXTERNAL_REFERENCE_AUDIT.md`
  - documents Stage 7o1 follow-up.
- `references/external/stage7o0_external_reference_audit.json`
  - marks three candidate families as promoted to owner-selectable Stage 7o1 candidates.
- `gui/zap2_gui/adapters/discord_pretls_guided_probe.py`
  - treats `capturePolicy.kind == external-reference-first-data-v1` as compatible with the guided Discord probe, so candidates can be observed before Stage 7o2 matrix automation.
- workspace/audit tests updated for the larger strategy catalog.

## Safety boundary

- Default strategy remains `manual-local`.
- No third-party scripts are executed.
- No service/install workflow is imported.
- Candidate capture remains owner UID scoped and owner-confirmed.
- UDP/voice/game-filter branches are deliberately deferred.
- The candidates are for observation matrix work, not final Discord promotion.

## Next stage

Stage 7o2 should build the observation matrix across:

```text
no zapret baseline
community-discord-pretls-diagnostic-pktdebug
community-discord-syndata-edge-flow-v2
reference-zapret2-generic-tls-fake
reference-linux-general-multisplit-like
reference-flowseal-simple-fake-like
```

The matrix should promote nothing until it shows a reproducible change in Discord updater behavior.
