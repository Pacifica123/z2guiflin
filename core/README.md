# Core source area

`core/zapret2/` contains a vendored snapshot of the upstream `zapret2` source tree from the archive supplied for the v0.3-alpha reboot.

Rules for this directory:

1. Keep upstream source mechanically separable from our GUI code.
2. Do not run upstream installer scripts from assistant-generated checks.
3. Treat future upstream refreshes as explicit source-import patches with a manifest and review notes.
4. Exclude compiled binary artifacts from Git unless the owner explicitly decides otherwise later.

The upstream license is preserved at `core/zapret2/docs/LICENSE.txt`.
