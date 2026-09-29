# Текущий статус проекта

## Статус релиза

Последняя принятая версия: `v0.6` (`0.6.0`). Текущий HEAD: P03 candidate toward `v0.7`.

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

## Ближайший приоритет после принятия P03 / перехода к v0.7

Основной долг находится не в добавлении очередной стратегии, а в надёжности продукта:

1. проверка совместимости профилей внутри пресета;
2. более ясный результат HAR/Blockcheck -> покрытие -> пресет;
3. стабильный service/autostart lifecycle;
4. управление DNS/hostlist/ipset;
5. упаковка для Arch;
6. отдельное завершение Discord Voice и tunnel routing.

Полный список: `KNOWN_GAPS_CHECKLISTS.md`.

### P03d portability contract (Arch-family)

Owner-host acceptance больше не считает `python3` из `PATH` системным Python: общий selector предпочитает
явный `ZAP2_PYTHON`, затем project venv, затем `/usr/bin/python3`, и только потом PATH fallback. Это устраняет
случай Manjaro/EndeavourOS с pyenv shim, когда pacman-модули (`pytest`, `PyQt6`) установлены для distro Python,
но невидимы shim-интерпретатору. Отсутствующий `--recover-root` после переезда host является `SKIP`, а не FAIL.
Acceptance может подготовить Arch host-local prerequisites и bounded helper; `untrusted/unknown` helper остаётся
fail-closed. Финальный PASS по-прежнему требует native build, parser, real nft/NFQUEUE canary и clean stop/revert.
