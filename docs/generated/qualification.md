# Генерируемый профиль квалификации P07

Исторические gates и обязательные сценарии P07 получены из замороженного qualification contract. Таблица не является результатом исполнения: фактические результаты сохраняются отдельно в qualification.json с привязкой к кандидату, времени, среде и артефактам. Локальные тесты не заменяют реальные привилегированные, сетевые, прикладные, пакетные и миграционные доказательства. Все обязательные ячейки проверяются совместно; отсутствие доказательства отражает результат исторической квалификации. v1.0 закрыта владельцем; текущая версия 1.1.0 описана в отдельном контракте.

| Gate | Claim | Evidence partitions | Falsifier |
|---|---|---|---|
| G01 | Truth-state | deterministic | local PASS promoted to route/app |
| G02 | VLESS live advertised lane | deterministic, liveNetwork | import fidelity/core validate/current-run TLS+HTTP not all PASS |
| G03 | Vesktop aggregate | deterministic, targetApp | mandatory HTTP/gateway/navigation missing or bypass promoted |
| G04 | Ownership and crash recovery | deterministic, privilegedOS | foreign resource cleanup, partial unrecoverable state or unsynchronized race |
| G05 | Finite privilege and TOCTOU | deterministic, privilegedOS, package | writable app imported root, mutable Plan/env/path authority or helper drift |
| G06 | Persistence/migration/downgrade | deterministic, migration/provenance | data loss, changed normalized semantics, unknown-newer write or silent downgrade |
| G07 | Whole-generation provenance | deterministic, privilegedOS, migration/provenance | mixed source/overlay/build/Lua/binary generation |
| G08 | Shipping semantics/rollback | deterministic, migration/provenance | unclassified shipping item or partial generation published |
| G09 | Canonical ontology | deterministic | legacy alias silently becomes distinct meaning |
| G10 | One immutable execution Plan | deterministic, privilegedOS | source/argv drift changes executed semantics without new confirmation |
| G11 | Executable ActionContract projections | deterministic | third registry or incomplete action/setting/concept projection |
| G12 | Context help and actionable errors | deterministic | WHAT/WHEN/effect/preconditions or cause/evidence/nextAction absent |
| G13 | Explicit CLI contradictions | deterministic | first-match silently ignores contradictory input |
| G14 | Current docs and generated freshness | deterministic | unlabeled historical instructions or stale generated reference |
| G15 | Clean Arch distribution lifecycle | deterministic, package | checkout/PYTHONPATH dependency, helper writable or user data deleted |
| G16 | Bounded partitioned evidence floor | deterministic, privilegedOS, liveNetwork, targetApp, package, migration/provenance | unbounded child, missing MUST partition or scope promoted |
| G17 | Independent identity axes | deterministic | product/version used as evidence/schema/core identity |
| G18 | SOCKS containment | deterministic, privilegedOS, targetApp | loopback/random port treated as authentication; bind/auth/UDP/app-access undeclared |
| G19 | Deliberate-failure support assessment | deterministic, review | raw credential, missing plan/run/evidence/verdict context or independent actionability assessment |
| G20 | Compositional golden journeys | deterministic, privilegedOS, liveNetwork, targetApp, package, migration/provenance | any mandatory J branch incomplete or failure undeclared |
| G21 | Review/PC/SA/current freeze integrity | deterministic, review | criterion weakening, stale candidate binding or self-issued final review |

| Journey | Claim | Partitions |
|---|---|---|
| J1 | Clean install → launch → plan → owned privilege → status/revert/exit | deterministic, package, privilegedOS |
| J2 | Preset → immutable Plan → confirm → apply → observe → revert | deterministic, privilegedOS |
| J3 | Crash cutpoint → restart → ownership → safe reconcile; foreign survives | deterministic, privilegedOS |
| J4 | VLESS import → fidelity → core → graph → supported launch OR declared bounded failure | deterministic, liveNetwork |
| J5 | Diagnostic → typed evidence, no hidden persistent/system mutation | deterministic |
| J6 | RU/EN/technical unknown concept → help → pre/effect → safe action | deterministic |
| J7 | Predecessor → backup/migration receipt → same promised normalized capability | deterministic, migration/provenance, package |

[Контракт](../developer/P07_PATCH_CONTRACT.md) · [Закрытие v1](../operations/v1-qualification.md).
