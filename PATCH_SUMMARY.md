# Patch summary

## Title

Flat pastel icons across GUI sections and tabs

## What changed

- added a small flat pastel icon set under `gui/zap2_gui/assets/icons/`;
- added `gui/zap2_gui/ui_icons.py` helper for loading section/action icons;
- applied icons to all top-level tabs: Overview, Core, Strategies, Diagnostics, Tunnel, Settings, Logs;
- applied icons to Logs sub-tabs and the main Overview action buttons;
- kept the visual language minimalistic: flat, pastel, mono/duotone, no 3D styling;
- documented the icon design approach in `docs/GUI_FLAT_PASTEL_ICONS.md`;
- added tests that verify the icon assets exist for all navigation sections and key GUI actions.

## Why

The GUI had become more useful functionally but still looked overly dark and heavy. This patch introduces a calmer flat visual layer without turning the interface into a colorful dashboard.

## Notes

This patch does not change the DPI strategy logic. It only improves visual clarity and section recognition in the GUI.
