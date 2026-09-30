# P07 — compositional qualification v1.0 RC7

База 65b60b2/post-P06; кандидат 1.0.0rc7. Это qualification patch, а не ложное закрытие final 1.0.0. Сохранены 119 ActionContract, 117 legacy selectors, dispatcher/app/helper source и точная P03 generation.

Добавлены PC/profile/falsifiers, immutable source/release binding, G01–G21/J1–J7 evidence matrix, predecessor migration policy, bounded L0–L2 test groups/JUnit и строгая привязка owner artifacts к digest/time/env/scope. Единая приёмка devctl и shell — --p07. Отсутствующие MUST owner/native/live/app/review receipts блокируют final; runner не меняет version/tag.

PRE выявил P06 same-release access defect: active session блокировала даже новый installed status/stop. Исправлен порядок idempotence/upgrade gate; состояние и чужие ресурсы не очищаются автоматически. Downgrade workspace не перезаписывает более новую product version; неизвестная версия требует explicit migration. Оба изменения отражены в SA. Support расширен только безопасными Plan/Run/log event projections для проверки deliberate-failure actionability/redaction.

Архив содержит воспроизводимый source release, SHA-pinned Arch PKGBUILD, полные deterministic/baseline logs и partitioned report. Clean Arch predecessor→candidate install/upgrade/uninstall, реальный privilege lifecycle, live VLESS, Vesktop aggregate и independent review выполняются отдельно на owner host. Результаты тестов в evidence не повышаются до этих claims.

После исправления SA-P07-03 `--p07` является check применения RC (freeze/projections/полный L0–L2); `--p07-release` является строгой финальной квалификацией по всем G01–G21/J1–J7. Оба режима используют один runner и сохраняют полную matrix. Owner предыдущий RC7: 651/651 tests PASS, qualification BLOCKED без receipts; это историческое наблюдение, а не PASS нового freeze.
