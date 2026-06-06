# Windows GUI reference digest

The Windows GUI archive is not the implementation base for the Linux reboot. It is a product reference: it shows what kinds of user-facing affordances are useful around `zapret`/`zapret2`.

## Ideas to preserve

### Toolbox/apothecary philosophy

The reference GUI presents strategies as a set of available remedies rather than a single universal magic button. The Linux product should keep that idea: multiple profiles, visible trade-offs, and the ability for the owner to add or modify strategies.

### Presets, profiles and ordering

The Windows tree has rich vocabulary around presets, profiles, folders, ordering, raw editors and strategy resolution. The Linux reboot should eventually model strategies as first-class data, not as hard-coded buttons.

### Diagnostics-first workflow

Important areas from the reference include blockcheck, DNS diagnostics, logs, support bundles and runtime health checks. For Linux, the first version should prefer read-only diagnostics before privileged apply/start actions.

### Orchestrator/scanner idea

The reference includes strategy scanning/orchestration concepts. The Linux product can later use a similar idea as a developer tool: try candidate strategies, record results, and help choose the next action.

### Explicit runtime state

The Windows GUI contains many modules around process/runtime monitoring, startup coordination, workers and log tailing. Linux should keep runtime state explicit and inspectable rather than hiding it behind a single “installed/not installed” label.

### Settings and host/domain management

DNS, hosts, hostlists, ipsets, blobs and program settings are product areas worth preserving conceptually. Their Linux implementation must be adapted to Linux paths and privilege boundaries.

## Ideas not to copy directly

- Windows registry assumptions;
- Task Scheduler/NSSM service model;
- WinDivert-specific runtime behavior;
- Defender/antivirus-specific UX;
- Windows packaging and PyInstaller assumptions;
- direct Windows paths and batch-file strategy execution.

## Translation to Linux architecture

| Reference idea | Linux reboot direction |
| --- | --- |
| Presets/profiles | Project/user strategy registry |
| Blockcheck | Read-only diagnostics first, controlled active checks later |
| Autostart/service controls | Owner-confirmed systemd/user-service plans later |
| Logs/support bundle | Local diagnostic report export |
| Raw preset editing | Text/config editor with validation |
| Strategy scan | Developer-owner experiment runner |

The reference is valuable because of product shape, not because its Windows internals should be ported one-to-one.
