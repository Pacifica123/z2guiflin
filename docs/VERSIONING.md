# Versioning policy

## Current product label

```text
v0.3-alpha
```

The project starts at `v0.3-alpha` even though the code tree is rebooted. The label continues the product history while acknowledging a new implementation baseline.

## Shape

Product labels use:

```text
v<major>.<minor>-<phase>[-hf_<shortFixName>]
```

Phases:

- `alpha` opens a cycle and may span many devctl patches;
- `beta` means the cycle goal is implemented enough for concentrated validation;
- `dev` means the owner is using it for longer real-world testing;
- `stable` may be declared only by the owner.

## v0.3-alpha stage ids

The new stream resets stage numbering under the product label:

```text
v0.3-alpha_stage_1
v0.3-alpha_stage_2
v0.3-alpha_stage_3
```

Do not continue the historical Stage 50+ numbering. Historical references remain valid as old-line notes, not as the active sequence.

## Promotion rules

- The assistant must not promote to `stable` on its own.
- Do not rename every patch as a new product version.
- Use the devctl patch id for patch identity and the product label for milestone identity.
- Hotfix suffixes are for `beta` and `dev`, not for ordinary `alpha` patch flow.
