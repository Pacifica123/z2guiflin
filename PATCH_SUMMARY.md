# Patch summary

## Title

Add specific Zapret readiness blocker for combined launch

## What changed

- Launch Composer now checks selected supported components before starting anything.
- If `zapret-default` is selected but `core/zapret2/nfq2/nfqws2` is missing or not executable, combined start is blocked before starting VLESS.
- Added explicit readiness values for Zapret:
  - `needs nfqws2 build`
  - `nfqws2 not executable`
  - `ready`
- Added classifier code `Z2-ZAPRET-BINARY-MISSING`.
- Updated launch error classifier documentation.
- Added regression tests for the precheck and classifier priority.

## Why

The previous behavior correctly reported `Z2-LAUNCH-PARTIAL`, but the real cause was more specific: Zapret did not start because `nfqws2` was missing. The GUI should show that cause directly and avoid starting only the VLESS half of a selected combined launch.
