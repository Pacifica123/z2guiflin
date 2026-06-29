# Patch summary

## Title

Fix Runtime Logs QtCore binding name

## What changed

- replaced stale `QtCore.QSize(...)` calls in `runtime_logs.py` with `_QtCore.QSize(...)`;
- added a static regression test for the local Qt binding variable name.

## Why

The minimal line icons patch added icon sizes in the Logs page but used the wrong variable name. The GUI crashed at startup with `NameError: name 'QtCore' is not defined`.
