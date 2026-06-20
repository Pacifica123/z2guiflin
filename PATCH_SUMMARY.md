# v0.4-alpha Stage 7r — Two-pane Diagnostics layout polish

Stage 7r is a follow-up UI-only patch for the Diagnostics / Blockcheck lab page.
It addresses the visual issues seen after Stage 7q: the output pane was still
pushed below the visible area, the intro/header area felt clipped, and the
single narrow centered column left large empty side margins.

## Updated

- Reworked the Diagnostics page into a compact two-pane layout:
  - left pane: Blockcheck scan parameters;
  - right pane: action buttons, status pill, and output/log pane.
- Increased the usable content lane from `940px` to `1080px`, while keeping a
  bounded maximum width so the page does not become edge-to-edge on large screens.
- Reduced the parameter form width from the Stage 7q wide single-column layout
  to a `560px` minimum / `620px` maximum pane.
- Reduced vertical control heights and grid spacing so the form no longer pushes
  the output pane off the bottom of a 768px-tall window.
- Converted the action buttons from two horizontal rows into a compact grid in
  the right pane.
- Reduced the output minimum height from `320px` to `220px` and removed the old
  output maximum width so it can expand inside the right pane.
- Kept the scroll area as a safety fallback for smaller windows, but the normal
  1240px-ish manual-test window should now show header, controls, status, and a
  usable log pane without the bottom being cut off.
- Updated source-level UI tests to lock in the two-pane Diagnostics contract.

## Scope

- No blockcheck execution, sudo, tunnel, firewall, strategy, service, zapret2
  core, or network behavior is changed.
- This patch only affects PyQt Diagnostics layout/source-level UI tests.

## Checks

- `python -m py_compile gui/zap2_gui/widgets/blockcheck_lab.py gui/zap2_gui/windows/main_window.py`
- `PYTHONPATH=gui python -m pytest -q tests/test_gui_shell_skeleton.py tests/test_blockcheck_gui_lab.py tests/test_stage7d_blockcheck_guard_and_ui.py tests/test_stage7e_blockcheck_lab_human_log_ui.py tests/test_stage7f_blockcheck_budget_ui.py tests/test_stage7g_blockcheck_ui_layout.py tests/test_stage7k_ui_and_community_v2.py tests/test_nfqws_privilege_order_and_gui_compact.py`

## Note

A full-suite `pytest -q -x` still stops on the pre-existing vendored-core
inventory mismatch: the tree has `core/zapret2/lua/custom_funcs.lua`, while the
committed `CORE_INVENTORY.json` snapshot still records the older 245-file core.
This UI patch does not change that snapshot.
