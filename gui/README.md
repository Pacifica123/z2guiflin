# GUI package

`gui/` contains only our application-side Python code. It must not absorb upstream engine sources and must not perform privileged host mutations during import.

Initial package responsibilities:

- know the repository layout;
- read vendored-core metadata;
- expose a future GUI shell entry point;
- keep privileged operations behind explicit user-owned plans.

The real UI can be introduced incrementally after the source tree and product rules stop moving.
