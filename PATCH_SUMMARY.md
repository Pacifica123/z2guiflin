# v0.4-alpha Stage 7s — Diagnostics spacing and header reflow polish

Stage 7s is a follow-up UI-only patch for the Diagnostics / Blockcheck lab page.
It focuses on the remaining visual defects seen after Stage 7r:
- the explanatory intro text could still look clipped/tight under the page title;
- the left scan form still had awkward dead space around labels and the preset hint row;
- the scan rows felt too loose vertically;
- the right log pane needed a bit more guaranteed height to stay comfortable.

## Updated

- Increased the effective Diagnostics content lane from `1080px` to `1160px`.
- Increased the right-side minimum width from `320px` to `360px`.
- Increased the log/output minimum height from `220px` to `300px`.
- Reworked the content wrapper margins/spacing to reduce the cramped header feeling.
- Stopped centering the entire Diagnostics body; the page now lays out naturally in the content lane instead of floating with odd side balance.
- Tightened the form grid with explicit inner margins and smaller vertical spacing.
- Reduced the label-column widths and right-aligned labels so controls read as a tighter block.
- Moved the service-target preset hint row to span the full form width, eliminating the awkward empty pocket under the first label column.
- Slightly widened the left form box and widened long combo/input maximum widths.
- Slightly reduced compact-control and action-button heights to make the parameter stack denser.
- Preserved the Stage 7r two-pane structure, scroll fallback, and all blockcheck execution behavior.
- Updated source-level UI tests to lock the new Stage 7s sizing contract.

## Scope

- No changes to blockcheck execution, sudo flow, tunnel/runtime behavior, strategy logic, service-target logic, or zapret2 core.
- This patch only affects Diagnostics layout polish and the source-level tests that describe it.

## Checks

- `python -m py_compile gui/zap2_gui/widgets/blockcheck_lab.py gui/zap2_gui/windows/main_window.py`
- `PYTHONPATH=gui python -m pytest -q tests/test_gui_shell_skeleton.py tests/test_blockcheck_gui_lab.py tests/test_stage7d_blockcheck_guard_and_ui.py tests/test_stage7e_blockcheck_lab_human_log_ui.py tests/test_stage7f_blockcheck_budget_ui.py tests/test_stage7g_blockcheck_ui_layout.py tests/test_stage7k_ui_and_community_v2.py tests/test_nfqws_privilege_order_and_gui_compact.py`
