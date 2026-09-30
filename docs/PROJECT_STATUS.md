# Текущий статус проекта

## Статус релиза

Последняя принятая версия: `v0.7` (`0.7.0`). P03f owner-host acceptance завершён с `READY_FOR_USE_WITHIN_P03`. P04a и P04b приняты (`READY_FOR_USE_WITHIN_P04A`, `READY_FOR_USE_WITHIN_P04B`). Текущий HEAD: P04c ActionContract dispatcher foundation toward `v0.8`.

Это рабочий персональный инструмент для исследования и запуска стратегий обхода DPI на Arch-family Linux (включая Arch, EndeavourOS и Manjaro). Версия фиксирует зрелость приложения и его диагностического/runtime-контура. Она не фиксирует одну универсальную рабочую стратегию.

## Подтверждённые возможности

- GUI запускается локально через `./run.sh`.
- Vendored-ядро инвентаризируется, а сборка описана явным plan.
- Пресеты состоят из упорядоченных профилей с фильтром, диапазоном, направлением и стратегией.
- Blockcheck Lab умеет работать с сервисными целями, сохранять результаты и экспортировать стратегии.
- HAR workbench разбирает HAR любого ресурса, группирует проблемные hosts и предлагает кандидатов для покрытия.
- Runtime использует plan/hash/confirmation, owner-scoped `nftables` table + marker, детерминированную NFQUEUE, process identity (`boot_id`/starttime/cmdline digest + strict `exe` when observable; expected dropped UID/GID fallback when Linux hides `/proc/<pid>/exe`) и управляемый `nfqws2`.
- Apply/revert используют checked nft batch, lifecycle lock и read-only reconciliation вместо слепого удаления одноимённой table.
- Security IP blocklist живёт в отдельной owned nft table: outbound C2/malicious destinations UID-scoped, тяжёлый inbound opt-in, обновления используют validated immutable generations и last-known-good fallback.
- P02: GUI остаётся unprivileged; `sudo -A` запускает только root-owned finite executor, который revalidate PlanHash и не импортирует writable workspace Python.
- Есть отдельная экспериментальная ветка SOCKS5/VLESS с внешним core, redacted-хранилищем профиля и probes.
- В целевой среде владельца существуют стратегии, которые помогают YouTube и основному desktop Discord: запуску и сообщениям.

## Неподтверждённые или нестабильные области

- Нет универсального пресета для всех сетей.
- Конструктор не гарантирует, что набор отдельных рабочих профилей образует рабочий пресет.
- Discord Voice/UDP не доведён до стабильного результата.
- Tunnel lane не является прозрачным системным VPN и зависит от внешнего core/upstream.
- P02: `systemd` service mode truth=`plan-only`; privileged service execution staged до отдельного finite executor action.
- Нет AUR-пакета и общего updater vendored core/hostlist/ipset. Security-IP blocklist имеет отдельный явный updater/timer и не подменяет этот будущий механизм.
- Реальные сетевые результаты нельзя проверить автономными тестами проекта.

## Как трактовать неудачную стратегию

Неудача стратегии не означает автоматически дефект GUI или runtime. Сначала проверяются уровни:

```text
ядро собрано
-> nftables применён
-> NFQUEUE совпадает
-> nfqws2 жив
-> нужные пакеты входят в capture scope
-> hostlist/ipset покрывает цель
-> порядок профилей не перекрывает нужный профиль
-> стратегия подходит текущему DPI
-> приложение действительно использует проверяемый маршрут
```

Если нижние уровни исправны, результат может зависеть от конкретного DPI и маршрута. В таком случае проект должен дать наблюдение и воспроизводимый отчёт, а не изображать гарантированную починку.

## Ближайший приоритет: P04 normalized semantics / ActionContract

Следующая архитектурная задача — не очередная стратегия, а устранение semantic/command drift:

1. P04a фиксирует re-forensics, REP/CLI/S-INSTALL evidence и canonical ontology;
2. P04b вводит resource-location contract и материализует один immutable Plan из разных source/import representations;
3. P04c переводит bounded runtime/default slice на executable ActionContract/dispatcher и ставит contradiction gate перед всеми 117 legacy action selectors;
4. P04d мигрирует оставшиеся 91 legacy-only selector destination и закрывает 100% coverage/lint/generated projection/roundtrip acceptance перед P05.

Подробно: `P04_REFORENSICS.md`. Остальные продуктовые пробелы остаются в `KNOWN_GAPS_CHECKLISTS.md`.


### P04c action authority

Canonical `--action <contract-id>` и 26 legacy selector destinations сходятся в одном dispatcher для 28 ActionContracts. Все 117 post-P04b legacy top-level action selectors проходят единый contradiction gate до handler; first-match ordering больше не может молча выбирать действие при противоречивом argv. Основные GUI Default workflow tooltips проецируются из тех же contracts. Полная миграция ещё не завершена: 91 selector destination остаётся legacy-only до P04d.

### P04b execution authority

Runtime recipe теперь materialize как `ImmutableExecutionPlan`: ordered argv + logical runtime resources с SHA-256, без абсолютного checkout path в hash. `presetPath` является execution source для shipping strategies; legacy `runtimeArgs` остаётся compatibility metadata и не может изменить Plan при drift. Resource discovery имеет явный provenance (`root` / `ZAP2_RESOURCE_ROOT` / verified checkout), но полный installed bundle и writable-state separation ещё открыты.

### P03d portability contract (Arch-family)

Owner-host acceptance больше не считает `python3` из `PATH` системным Python: общий selector предпочитает
явный `ZAP2_PYTHON`, затем project venv, затем `/usr/bin/python3`, и только потом PATH fallback. Это устраняет
случай Manjaro/EndeavourOS с pyenv shim, когда pacman-модули (`pytest`, `PyQt6`) установлены для distro Python,
но невидимы shim-интерпретатору. Отсутствующий `--recover-root` после переезда host является `SKIP`, а не FAIL.
Acceptance может подготовить Arch host-local prerequisites и bounded helper; `untrusted/unknown` helper остаётся
fail-closed. Финальный PASS по-прежнему требует native build, parser, real nft/NFQUEUE canary и clean stop/revert.


### P03f owner-host acceptance correction

A real Manjaro canary proved that nft/NFQUEUE start succeeds but bounded sessions could become
`unknown` after privilege drop because `dropIdentity` was not copied from the confirmed bounded
start-plan into the session receipt. P03f fixes the receipt propagation and adds strict one-time
recovery for already-running P03/P03e sessions. P03f acceptance завершён: owner-host runner достиг `READY_FOR_USE_WITHIN_P03`, поэтому baseline повышен до `v0.7`.
