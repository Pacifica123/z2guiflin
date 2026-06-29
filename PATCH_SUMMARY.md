# Patch summary

## Title

Redesign GUI icons as minimal line icons

## What changed

- replaced the previous boxed pastel icons with simpler line-style SVG icons;
- removed colored background boxes and dense inner details from all GUI icons;
- kept one calm pastel stroke color per icon;
- fixed the Overview start/stop button so the old text symbol `▶/■` no longer overlaps the new SVG icon;
- added icon sizes for Overview and Logs action buttons;
- documented the revised visual rule in `docs/GUI_FLAT_PASTEL_ICONS.md`;
- added regression checks for background-box icons and the start button text/icon overlap.

## Why

The first icon patch was too decorative and visually noisy. The reference style is closer to small flat line icons used as navigation/action hints, not standalone pictograms.
