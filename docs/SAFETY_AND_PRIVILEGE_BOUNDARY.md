# Safety and privilege boundary

## Baseline

Until `v1-stable`, the guaranteed user is the owner/developer. The product should therefore favor forward development and transparent local control over excessive UX paternalism.

This is not permission for hidden system mutation. It is a decision to stop blocking development merely because the eventual product domain includes privileged Linux operations.

## What automated patches may do

Automated devctl checks may:

- parse Python files;
- verify repository structure;
- read vendored metadata;
- validate docs and source presence;
- run pure unit tests for our code.

Automated checks should not:

- call `sudo`;
- install packages;
- run upstream installer scripts;
- change system services;
- change firewall/nftables/iptables state;
- download executable content from the network.

## What the owner may do locally

The owner may run privileged commands locally when future documentation or the GUI produces a clear plan. Those actions should be treated as owner-confirmed development operations, not assistant-side automation.

Future privileged workflows should follow this shape:

```text
collect facts -> generate command plan -> show exact plan -> owner confirms -> run locally -> log result -> offer rollback notes
```

## No remote bootstrap principle

The product should not depend on `curl | sh`, blind remote installers, or automatic upstream replacement. The core source is vendored under `core/zapret2/` and updated only by explicit source-import patches.

## Practical safety attitude

Safety for this project means:

- visible boundaries;
- minimal hidden state;
- local source ownership;
- reproducible patches;
- logs and reports;
- refusal to run privileged commands inside the assistant environment;
- respect for the owner’s ability to run their own development machine.
