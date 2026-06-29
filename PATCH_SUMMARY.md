# Patch summary

## Title

Fix QTabWidget icon overload order

## What changed

- fixed top-level tab creation to call `QTabWidget.addTab(widget, icon, label)`;
- fixed Logs sub-tabs to use the same PyQt overload order;
- added a regression test for the icon tab argument order.

## Why

The flat pastel icon patch used the wrong overload order: `addTab(icon, widget, label)`. PyQt expects the widget first, so the GUI crashed on startup.
