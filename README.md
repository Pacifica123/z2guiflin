# Zap2 GUI Linux — v0.3-alpha native-core reboot

This repository is a fresh product line for a Linux GUI around a vendored copy of `zapret2` by bol-van. The previous Zapret2GUIfLin tree is treated as a notebook of drafts, tests and product experiments, not as the live architecture.

## What changed in v0.3-alpha

`v0.3-alpha` starts from a clean structure:

```text
core/      vendored upstream engine source and import metadata
gui/       our GUI-side Python package and future application shell
docs/      product strategy, reference notes and development rules
tools/     repository checks that never require network, sudo or service control
tests/     small structural tests for the new baseline
```

The key architectural decision is that the upstream engine is part of the repository source tree. The application must not bootstrap itself with remote `curl` downloads or opaque installer scripts. Future privileged operations belong to explicit, reviewable user-run plans.

## Current status

This patch is a bootstrap, not a working end-user application. It imports the upstream source into `core/zapret2/`, creates a minimal GUI package under `gui/zap2_gui/`, and records the strategy for the next patch series.

```bash
python tools/check_project_tree.py
python -m compileall -q gui tools tests
```

These checks are intentionally read-only. They do not build the C engine, do not install packages, do not touch firewall/service state, and do not need elevated privileges.

## Development rule

All future work should continue through `devctl` patch archives. The assistant should generate patches and documentation; the owner/developer decides when to run local privileged commands on their own machine.
