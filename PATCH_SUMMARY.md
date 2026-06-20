# v0.4-alpha Stage 7u — Scan form no-stretch compaction

Stage 7t reduced some widget sizes, but the visual screenshot showed the real
problem: the `Параметры scan` group box was still stretching vertically to match
its right-hand neighbor, so the scan controls looked almost unchanged and the
rows stayed too far apart.

Stage 7u fixes that directly.

## Updated

- Prevented the `Параметры scan` group box from vertically stretching with the
  taller output/log pane.
- Added a maximum height for the scan group box so its controls stay packed near
  the top instead of being spread across the full page height.
- Set the scan group box vertical size policy to `Maximum`.
- Added the scan group box to the two-pane body with `AlignTop`.
- Kept the Stage 7t smaller control sizes, tighter grid margins, smaller helper
  text, and narrower label/control columns.
- Preserved the right `Actions` pane, status pill, output pane, scroll fallback,
  and all blockcheck behavior unchanged.

## Scope

- UI-only patch for Diagnostics layout density.
- No changes to blockcheck execution, sudo flow, target selection, strategy export,
  tournament logic, tunnel logic, or zapret2 core.

## Checks

- `python -m py_compile gui/zap2_gui/widgets/blockcheck_lab.py gui/zap2_gui/windows/main_window.py`
- `PYTHONPATH=gui python -m pytest -q tests/test_gui_shell_skeleton.py tests/test_blockcheck_gui_lab.py tests/test_stage7d_blockcheck_guard_and_ui.py tests/test_stage7e_blockcheck_lab_human_log_ui.py tests/test_stage7f_blockcheck_budget_ui.py tests/test_stage7g_blockcheck_ui_layout.py tests/test_stage7k_ui_and_community_v2.py tests/test_nfqws_privilege_order_and_gui_compact.py`
