# 2026-10-21-version-1-2-0 — версия 1.2.0 и правило версий

Последний патч пачки A. Закрывает карточку «Версия продукта не растёт вместе с патчами».

## Что сделано

- Правило: пачка с фичами поднимает **minor**, пачка с исправлениями — **patch**. Записано в `docs/VERSIONING.md`
  (со списком всех привязок версии) и в `docs/developer/devctl.md`.
- Пачка A (навигация по пути пользователя + витрина) → **1.2.0** во всех привязках: `pyproject.toml`,
  `gui/zap2_gui/__init__.py` (`__version__`, `PRODUCT_LABEL = "v1.2"`, `DEVELOPMENT_LINE`), `docs/developer/v11-contract.json`
  (`candidateVersion`/`targetVersion`), freeze `runtime/v11/candidate-freeze.json`, закреплённые тесты, `docs/generated/reference.*`,
  `dist/arch/1.2.0` в README и документации.
- `runtime/v11` и `v11-contract.json` не переименованы: это имена контракта. `runtime/v11/container-validation.json` — историческое
  свидетельство о 1.1.0 и не трогается.
- `docs/developer/devctl.md`: требуемый devctl — не ниже 0.10.0, workspace `tgn`, репозиторий `pacifica123/z2guiflin`.
- Доска: карточка версии → «Сделано»; план пачки B (1.3.0) разложен по карточкам: DNS-слой, валидатор конфликтов профилей,
  миграция strat_collection → «Запланировано» с решениями владельца; новые карточки «Пресеты удобнее» и «Tor и мосты»;
  на карточке редактора hosts — что нашлось у loop-uh.

## Проверки

- `bash meta_tools/run_tests.sh` (закреплённые версии в тестах обновлены), `check_board.py`, freeze и generated reference пересчитаны.
