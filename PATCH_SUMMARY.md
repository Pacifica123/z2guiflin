# Внешний devctl ≥0.9.0 и живая доска долга

База aab420c, product 1.1.0 (версия не меняется). Первый патч пачки `2026-10-15-ready-to-patch-r1`.

Вендоренная копия devctl 0.6.7 (`meta_tools/devctl`) удалена: devctl — внешний инструмент ≥0.9.0, его конфигурация `.devctl/` живёт в корне workspace уровнем выше, а не в проекте. Правила применения патчей и пачек описаны в `docs/developer/devctl.md`. Две версии devctl создавали риск, что патч проверяется не тем инструментом, которым применяется.

Добавлена доска `board/board.json` (формат p2p_planner_bundle, импортируется в p2pKanban) — живой реестр долга вместо замороженного KNOWN_GAPS v0.4. Её источник — глобальное исследование 15.10.2026: upstream zapret2, wiki.zapret.moe, Windows-референс zapretgui. Каждый патч обязан обновлять доску и оставлять комментарий с patchId. Целостность доски проверяет `tools/gui_checks/check_board.py`, его вызывает `tests/test_board.py`.

Структурные проверки (`test_bootstrap_structure`, `check_project_tree`) теперь требуют `docs/developer/devctl.md` и `board/board.json` и запрещают `meta_tools/devctl`. v1.1 source freeze пересчитан (`p07_qualification.py --freeze`), потому что изменился набор файлов.
