# 2026-10-21-version-1-3-0 — версия 1.3.0

Последний патч пачки B. По правилу `docs/VERSIONING.md` пачка с фичами поднимает minor.

## Что сделано

- **1.3.0** во всех привязках: `pyproject.toml`, `gui/zap2_gui/__init__.py` (`__version__`, `PRODUCT_LABEL = "v1.3"`,
  `DEVELOPMENT_LINE = "v1.3 DNS, presets UX, Tor page and auto-update"`), `docs/developer/v11-contract.json`
  (`candidateVersion`/`targetVersion`), freeze `runtime/v11/candidate-freeze.json`, закреплённые тесты, `docs/generated/reference.*`,
  `dist/arch/1.3.0` в README и документации.
- Что вошло в 1.3.0 — в README, `docs/README.md`, `docs/PROJECT_STATUS.md`, `docs/VERSIONING.md`, `gui/README.md`.
- `docs/README.md` ссылается на пользовательские страницы (пресеты, Tor, вердикт сети, оркестратор).
- `docs/operations/lifecycle.md`: кнопка «Обновление» и что делать, если обновление отказывает
  (`--lifecycle-status`, `--lifecycle-confirm-stopped`).

## Проверки

- `bash meta_tools/run_tests.sh` (закреплённые версии в тестах обновлены), `check_board.py`, freeze и generated reference пересчитаны.
