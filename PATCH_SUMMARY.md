# Patch summary

## Title

Rework Tunnel tab into profile/core/route tabs and unify Overview toggle

## What changed

- replaced the cramped Tunnel tab stack with three sub-tabs:
  - `Профили VLESS`
  - `Tunnel core`
  - `Discord через SOCKS`
- added a redacted VLESS profile table similar to the Strategies table workflow;
- added `Сделать активным` for selecting a connection directly from the table;
- removed the visible guided CLI hint from the Tunnel tab;
- kept detailed route/core output in the lower output pane;
- changed the Overview main start/stop button to use selected Launch Composer components;
- the Overview indicator now says `Всё запущено` only when all selected supported components are actually running;
- added tests for redacted tunnel table rows, the tabbed Tunnel layout, and the unified Overview toggle contract.

## Why

The previous Tunnel UI was too crowded and made it unclear whether VLESS core was actually started. The main Overview button also did not match the component selection UI. This patch makes both flows explicit.
