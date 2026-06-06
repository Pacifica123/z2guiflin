# Project structure

```text
core/
  README.md
  zapret2/
    UPSTREAM_IMPORT.json
    UPSTREAM_IMPORT.md
    ... vendored upstream source ...

gui/
  README.md
  zap2_gui/
    __init__.py
    app.py
    core_inventory.py
    project_paths.py

docs/
  DEVELOPMENT_STRATEGY.md
  VERSIONING.md
  PROJECT_STRUCTURE.md
  SAFETY_AND_PRIVILEGE_BOUNDARY.md
  reference/
    windows_gui_feature_digest.md
    legacy_project_digest.md

tools/
  check_project_tree.py

tests/
  test_bootstrap_structure.py
```

## Separation rule

`core/` is upstream engine source. `gui/` is our product code. `docs/` describes decisions and reference behavior. Do not blur these areas by scattering GUI code into the core tree or by turning docs into executable install instructions.

## Core import rule

The imported source is intentionally vendored. Future updates should be explicit source refresh patches, not runtime auto-updates. The GUI may later offer “a new upstream exists” diagnostics, but applying that update is a developer decision.


## GUI framework rule

The active GUI framework is **PyQt**. The current tree may still contain only a minimal Python package, but future GUI shell work should target PyQt rather than PySide, GTK, Tkinter, Electron, a browser-first interface, or a CLI-only application.

Recommended future split:

```text
gui/zap2_gui/
  app.py              application entry point
  qt_app.py           PyQt QApplication bootstrap once the dependency lands
  windows/            top-level windows and navigation shell
  widgets/            reusable PyQt widgets
  models/             pure Python state/data models
  adapters/           core/build/diagnostic planning adapters
```

Qt-specific classes should stay near the UI layer. Core inventory, build-plan generation and safety/privilege planning should remain pure Python so they can be tested without a display server.
