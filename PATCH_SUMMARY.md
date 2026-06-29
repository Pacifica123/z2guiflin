# Patch summary: GUI-first runtime overview

Дата: 2026-06-29

## Изменения

- Добавлен `gui_first_overview.py`: read-only state machine для Overview.
- Overview tab теперь показывает selected/prepared/running/firewall state, а не только CLI-style status.
- Добавлена пользовательская кнопка `Проверить Discord` в Overview. Она вызывает guided probe без shell-команд.
- Ручные plan/confirm/command кнопки спрятаны за `Developer mode`.
- `gui_toggle_default_workflow` теперь включает GUI-first overview в вывод до и после действия.
- Добавлена CLI-команда `--gui-first-overview` как read-only контракт для тестов и dev fallback.
- Добавлена документация `docs/GUI_FIRST_RUNTIME_OVERVIEW.md`.
- Добавлены тесты `tests/test_gui_first_overview.py`.

## Проверки

```text
python3 -m py_compile gui/zap2_gui/adapters/gui_first_overview.py gui/zap2_gui/adapters/gui_runtime_controls.py gui/zap2_gui/widgets/runtime_controls.py gui/zap2_gui/app.py
PYTHONPATH=gui pytest -q tests/test_gui_first_overview.py tests/test_gui_toggle_and_runtime_logs.py tests/test_default_strategy_import_and_gui_controls.py::test_gui_runtime_controls_are_confirmation_gate_wrappers tests/test_default_strategy_import_and_gui_controls.py::test_gui_privileged_command_uses_sudo_askpass_not_terminal_password tests/test_default_strategy_import_and_gui_controls.py::test_default_status_cli_is_read_only tests/test_stage7n2_guided_pretls_probe.py::test_stage7n2_guided_probe_refuses_when_workflow_not_running
```


## 2026-06-29 GUI-first tables and copy buttons

- Added table-row model for GUI-first runtime overview.
- Added TSV/plain-text copy output for the overview table.
- Updated Overview tab to render selected/prepared/running/firewall state as a `QTableWidget`.
- Added `Копировать таблицу` and `Копировать вывод` buttons.
- Kept raw workflow controls behind Developer mode.
