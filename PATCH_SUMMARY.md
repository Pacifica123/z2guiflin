# v0.4-alpha Stage 7q — Compact diagnostics tab visual pass

Stage 7q is a UI-only pause from the Discord tunnel work. It cleans up the
Diagnostics / Blockcheck lab page so it is less wide, the log area is usable,
and the main run/stop controls are visually distinct without changing the
blockcheck execution logic.

## Updated

- Reduced the main window default size from `1320x900` to `1240x840` and the
  minimum size from `1060x720` to `960x680`, keeping the app usable on smaller
  screens.
- Narrowed the Blockcheck lab content lane to `940px` and introduced a shared
  `720px` section minimum for header, form, actions, status, and output.
- Made the Diagnostics output pane expand to the same section width instead of
  collapsing into a tiny narrow textbox.
- Replaced the text-heavy Blockcheck run/stop buttons with compact `▶` and `■`
  controls and object names for styling.
- Added lightweight page-local styling for the diagnostics title, group boxes,
  status pill, primary run button, stop button, and monospace log output.
- Updated source-level UI tests to lock in the compact layout and bounded window
  sizing.

## Scope

- No runtime, tunnel, zapret2 core, strategy, firewall, service, sudo, or network
  behavior is changed.
- This patch only affects the PyQt diagnostics layout, main-window sizing, and
  tests that assert those visual contracts.

## Checks

- `python -m py_compile gui/zap2_gui/widgets/blockcheck_lab.py gui/zap2_gui/windows/main_window.py`
- `PYTHONPATH=gui pytest -q tests/test_gui_shell_skeleton.py tests/test_blockcheck_gui_lab.py tests/test_stage7d_blockcheck_guard_and_ui.py tests/test_stage7e_blockcheck_lab_human_log_ui.py tests/test_stage7f_blockcheck_budget_ui.py tests/test_stage7g_blockcheck_ui_layout.py tests/test_stage7k_ui_and_community_v2.py tests/test_nfqws_privilege_order_and_gui_compact.py`

## Note

A full-suite pytest run still reaches an unrelated pre-existing vendored-core
inventory snapshot mismatch: the current tree contains `core/zapret2/lua/custom_funcs.lua`
while `CORE_INVENTORY.json` still records the older 245-file snapshot. This UI
patch does not touch that snapshot.
