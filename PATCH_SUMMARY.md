# P05 RC5 — глобальный поиск, справка и состояние

База: приложенный post-v0.8 archive, lineage `1addd90`. Product candidate: `0.9.0rc5` / `v0.9 RC5`; последний owner-accepted release — v0.8. Final 0.9.0 пока не назначен.

- Ctrl+K ищет 119 действий, canonical concepts и реальные настройки по RU/EN/technical terms, с ограниченными опечатками и детерминированным ranking.
- Exact action/concept help фокусируется в общем инспекторе; настройки — в реальном control. CLI-only действия получают справку и маршрут в раздел.
- Явный direct invoke ограничен safe read/validate contracts, идёт через прежний canonical dispatcher; mutation/probe/prepare/import/export не запускаются из palette.
- Contextual help содержит смысл, условия и эффект; ID и CLI раскрываются отдельно.
- Structured error envelope добавляет cause/evidence/semantic nextAction к прежнему classifier и banner tooltip/full text.
- Health разделяет runtime, local SOCKS, remote HTTPS/TLS и app mandatory predicates; использует P01 binding/requirements и P02 next_safe_action. Не сохраняет graph и не запускает network probes.
- Stop/dead/mismatched/unbound state не получает зелёный network/app health. Снимок требует явного refresh после изменений.
- Catalog/dispatcher/legacy CLI и исходные frozen receipts не переписываются; PRE зафиксирован в `runtime/p05/pre-forensics.json`.
- Текущие entry-point документы, версия и regression version assertions согласованы с RC5 candidate. Исторические stages явно помечены.

Единый профиль: `bash meta_tools/hyperpatch_acceptance.sh --p05`. Тот же pipeline включён в devctl manifest. Focused GUI tests и полный regression выполняются в временных копиях с изолированными настройками; все step/full pytest logs сохраняются в evidence ZIP.

Фактический результат проверок этой среды записан в `runtime/p05/container-validation.json`. Детерминированные P05 проверки могут пройти, пока full regression остаётся BLOCKED: контейнер не предоставляет корректный `/proc/<child-pid>`. Эти проверки не исключаются из owner acceptance.

Следующий DAG: RC5 owner acceptance → new HEAD re-forensics → решение о final SemVer → P06 productization → P07 qualification. Этот patch не создаёт owner receipt и не утверждает внешнюю доступность Discord.
