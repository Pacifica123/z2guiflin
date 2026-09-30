# Текущий статус проекта

## Статус релиза

Последняя принятая версия: **`v0.8` (`0.8.0`)**. P03f и P04a/P04b/P04c/P04d owner acceptance завершены; P04d достиг `READY_FOR_USE_WITHIN_P04D`, P04 закрыт. Текущий следующий provisional узел — **P05 discoverability/help/unified health UX**. Promotion и recompiled DAG: `V08_RELEASE_P05_HANDOFF.md`.

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

## Текущий приоритет: подготовленный P05 discoverability/help/unified health UX

P04 архитектурно закрыт и принят как v0.8. Следующий PRE строится не вокруг новой стратегии, а вокруг пользовательской discoverability-проекции существующих truth sources:

1. global action/concept search по RU/EN/technical terms из ActionContract/concept metadata;
2. contextual help без отдельного ручного registry;
3. structured errors `cause + evidence + nextAction`;
4. health projection, сохраняющая различия runtime/network/app и UNKNOWN/stale;
5. safe focus/invoke policy, которая не обходит Plan/confirmation/privilege.

Это пока **подготовленный контракт задачи**, а не реализованный P05. Перед первым P05 mutation patch обязателен новый re-forensics на принятом v0.8 HEAD. Подробно: `P05_REFORENSICS.md` и `V08_RELEASE_P05_HANDOFF.md`.

### P04d action authority / RC4

Все 117 historical selector destinations переводятся в canonical ActionContracts до исполнения; `runtime_plan` даёт три canonical actions, поэтому catalog закрыт на 119 actions/119 handlers. `main()` не содержит legacy first-match dispatch. Проверенные старые command bodies остаются selector-scoped compatibility executor только после contract selection. Generated bindings воспроизводимы из parser surface, canonical operands поддерживают legacy selector values, а projection metadata строится из единого ActionContract catalog. Подробности: `P04D_ACTION_CONTRACT_CLOSURE.md`.

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
