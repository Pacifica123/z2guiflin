# Development strategy — v0.3-alpha native-core reboot

## Decision

The old Zapret2GUIfLin line is closed as the active implementation baseline. Its archive remains useful as a draft notebook: it contains UI experiments, privilege-boundary notes, lifecycle ideas, tests, and terminology. The new product starts at `v0.3-alpha` with a clean repository shape and a vendored upstream core.

## Why restart

The previous chain spent many patches trying to wrap installation and update behavior safely. That was slow because the product kept orbiting around remote installation, shell orchestration and system-level side effects. The new direction removes that pressure: the engine source is inside the project, and the GUI is built around a known local source tree.

This does **not** mean the assistant should run privileged commands. It means the assistant should stop trying to hide necessary developer actions behind overprotective abstractions. The correct boundary is:

- the assistant writes patches, docs, adapters, plans and checks;
- checks are read-only unless explicitly scoped otherwise;
- the owner/developer may run privileged commands locally because the current product is single-user before `v1-stable`;
- any future privileged operation must be documented, visible and reversible enough for the owner to accept responsibility.

## Global goal for the v0.3 series

Build a Linux-first GUI that treats `core/zapret2/` as the native engine source and provides a controlled developer-owner workflow around it:

1. inspect the vendored core and show what is present;
2. build the engine locally from repository source;
3. expose strategy/profile configuration without hiding files from the developer;
4. provide read-only diagnostics and blockcheck-style discovery;
5. generate explicit run/apply plans for actions that need privileges;
6. only then introduce service/session management as an owner-confirmed layer.

This goal is deliberately too large for one or two patches. It should take a sequence of v0.3-alpha stages before the project can be promoted to `v0.3-beta`.

## Patch workflow

Future changes continue to use `devctl` zip patches:

```text
manifest.json
files/...
PATCH_SUMMARY.md
```

Patch naming should follow the version-qualified stage sequence:

```text
2026-06-06-v0.3-alpha_stage_1-native-core-reboot.devctl.patch.zip
2026-06-06-v0.3-alpha_stage_2-...
```

A patch should include:

- a concise product reason;
- a source-alignment note when it touches core or reference behavior;
- checks that do not generate bytecode artifacts outside devctl cleanup expectations;
- no network dependency unless explicitly approved for that patch;
- no `sudo`, service mutation or firewall mutation in automated checks.

## Assistant/developer boundary

The assistant should not attempt to run `sudo`, install packages, manipulate services, change firewall rules, or execute upstream installer scripts in its own environment. Those operations are either impossible in the sandbox or inappropriate for automated patch validation.

The owner may run such commands locally when they are part of the intended product, because until `v1-stable` the only guaranteed user is also the developer. The product should therefore optimize for transparent control rather than paternalistic blocking. Safety means clear ownership, dry-run capability, logs, and command visibility — not endless refusal to model the workflow.

## Preferred architecture

```text
core/zapret2/       upstream engine source, imported and reviewed as source
gui/zap2_gui/      Python GUI shell and application orchestration
docs/              strategy, reference and decision records
tools/             read-only repository checks and future developer helpers
tests/             structural and unit tests for our layer
```

The GUI must depend inward on narrow adapters, not on random shell snippets. Future adapters should represent operations as data first:

```text
inspect -> plan -> present -> owner confirms -> execute locally -> record result
```

## Near-term stage plan

### v0.3-alpha_stage_1 — bootstrap

Create the clean project tree, import core source, document the new rules, and preserve Windows GUI ideas as reference notes.

### v0.3-alpha_stage_2 — core inventory and build map

Add a read-only inventory model for Makefiles, C sources, Lua scripts, configs and docs. Produce a build-plan object but do not run a privileged install.

### v0.3-alpha_stage_3 — GUI shell skeleton

Create the initial Linux GUI shell with navigation placeholders: Overview, Core, Strategies, Diagnostics, Settings, Logs.

### v0.3-alpha_stage_4 — local build adapter

Add a local build command plan for the engine. The assistant-generated check may validate command construction, but actual host dependencies remain owner-controlled.

### v0.3-alpha_stage_5 — profile/strategy workspace

Represent strategies and hostlists as editable project/user data. Borrow the Windows GUI “toolbox/apothecary” philosophy without copying Windows-specific service assumptions.

### v0.3-alpha_stage_6+ — controlled runtime lifecycle

Introduce explicit run/apply/session/service plans with confirmation, logs and rollback notes. Do not merge this with bootstrap.

## Definition of done for v0.3-beta

`v0.3-beta` can be considered only when the project has a working GUI skeleton, a local core build path, visible strategy/profile management, diagnostics, and an explicit owner-confirmed path for any privileged action. Beta does not require multi-user polish.
