# Upstream import notes

This directory is a vendored source snapshot imported from `zapret2-core-from_bolvan.zip` for the `v0.3-alpha` reboot.

- Upstream: `bol-van/zapret2`
- Imported files: `245`
- Excluded files: `9`
- License preserved: `docs/LICENSE.txt`
- Content digest over imported files: `9d57e8fdee29938d560a390f976def49d4692f8dfda7e59c7df4a48fffe773d5`

The excluded files are CI metadata or compiled/binary artifacts from the supplied archive. They are listed in `UPSTREAM_IMPORT.json` so a future patch can deliberately re-evaluate them if needed.

The GUI layer must treat this directory as source input. It must not rewrite it casually and must not execute installer scripts as part of automated validation.
