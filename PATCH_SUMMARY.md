# v0.4-alpha Stage 7t — Compact Scan Parameters polish

Stage 7t is a small follow-up UI-only patch for the Diagnostics / Blockcheck lab page.
After Stage 7s the overall two-pane layout was close to acceptable, but the
left `Параметры scan` area still looked looser and bulkier than the `Actions`
panel. This patch compacts the scan-parameter area while preserving all current
blockcheck behavior and control semantics.

## Updated

- Tightened the internal `Параметры scan` grid margins and row spacing.
- Reduced the height of the larger top controls (`Service target`, `Домены/URI`,
  `Candidate mode`) from `34px` to `32px`.
- Reduced compact combo/spin heights from `30px` to `28px`.
- Reduced compact combo/spin minimum widths so the two-column parameter pairs
  read as a denser, neater block.
- Reduced the label-column minimum widths and kept right-aligned labels so the
  left form reads more like a compact settings sheet and less like a sparse form.
- Reduced the preset hint height and width slightly and kept it spanning the full
  form width.
- Slightly narrowed the scan form maximum width and section minimum width so the
  overall left pane feels more balanced next to the `Actions` pane.
- Added a small style hook for the scan group box and slightly smaller helper-text
  styling for the preset hint.
- Preserved the Stage 7s/7r two-pane structure, status pill, output pane, scroll
  fallback, and all blockcheck/tunnel/runtime logic unchanged.

## Scope

- No changes to blockcheck execution, sudo flow, target selection, strategy export,
  tournament logic, tunnel logic, or zapret2 core.
- Only the Diagnostics UI layout density and related source-level UI tests changed.

## Checks

- `python -m py_compile gui/zap2_gui/widgets/blockcheck_lab.py gui/zap2_gui/windows/main_window.py`
- `PYTHONPATH=gui python -m pytest -q tests/test_gui_shell_skeleton.py tests/test_blockcheck_gui_lab.py tests/test_stage7d_blockcheck_guard_and_ui.py tests/test_stage7e_blockcheck_lab_human_log_ui.py tests/test_stage7f_blockcheck_budget_ui.py tests/test_stage7g_blockcheck_ui_layout.py tests/test_stage7k_ui_and_community_v2.py tests/test_nfqws_privilege_order_and_gui_compact.py`
