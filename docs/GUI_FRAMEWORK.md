# GUI framework decision

## Decision

The Linux GUI for this project will be built on **PyQt**. Unless a later owner-approved decision record changes this, “PyQt” means the PyQt 6 line.

## Why PyQt

The project needs a real desktop GUI with structured navigation, logs, diagnostics, settings, profile editors and confirmation dialogs. Qt is a good fit for that shape, and PyQt keeps the codebase in Python while still allowing a mature native desktop shell.

## Scope of this decision

This patch only records the decision. It does not add PyQt as a runtime dependency yet and does not require PyQt to be installed for bootstrap checks. The dependency should be introduced together with the first real GUI shell so the project can keep documentation-only and structural stages lightweight.

## Architectural rule

PyQt belongs at the application shell and widget layer. Non-UI logic should stay pure Python:

- repository layout discovery;
- vendored-core inventory;
- build-plan generation;
- diagnostics planning;
- privilege/sudo command plans;
- log parsing and report models.

This keeps tests runnable without a display server and prevents the GUI from becoming the only way to reason about the project.

## Non-goals

Do not introduce PySide, GTK, Tkinter, Electron, a browser-first UI, or a terminal-first UI as the active shell direction unless the owner explicitly reopens the GUI framework decision.
