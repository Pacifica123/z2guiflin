# GUI package

`gui/` contains our application-side Python code and will grow into a PyQt desktop GUI. It must not absorb upstream engine sources and must not perform privileged host mutations during import.

Initial package responsibilities before the PyQt shell lands:

- know the repository layout;
- read vendored-core metadata;
- expose a future GUI shell entry point;
- keep privileged operations behind explicit user-owned plans.

The real UI should be introduced incrementally as a PyQt shell after the source tree and product rules stop moving. Do not switch the planned shell to PySide, GTK, Tkinter, Electron, or a CLI-only interface without an explicit owner decision.
