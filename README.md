# Zap2 GUI Linux — v0.8 RC4 candidate (P04d)

`z2guiflin` — персональный GUI и набор диагностических инструментов для Arch Linux вокруг vendored-копии `zapret2` от bol-van. Проект помогает исследовать блокировки, собирать и запускать стратегии `nfqws2`, работать с `nftables`, а также проверять отдельную ветку SOCKS5/VLESS.

Последняя принятая продуктовая версия — `v0.7`: P03f завершил pinned zapret2 1.0.6 generation migration и прошёл owner-host hyperpatch acceptance (`READY_FOR_USE_WITHIN_P03`). P04a, P04b и P04c приняты владельцем (`READY_FOR_USE_WITHIN_P04A/B/C`). Текущий HEAD — P04d/RC4 candidate (`0.8.0rc4`): все 117 historical CLI selectors contract-backed, 119 canonical ActionContracts закрыты executable dispatcher и first-match authority удалён из `main()`. Как и раньше, версия фиксирует рабочую платформу, а не универсальную стратегию обхода. В целевой среде владельца отдельные стратегии уже помогают YouTube и запуску/сообщениям Discord. Другие комбинации могут не давать результата даже для YouTube. Это зависит от провайдера, DPI, маршрута, DNS, приложения и конкретной стратегии; приложение не может гарантировать одинаковый результат во всех сетях.

## Быстрый запуск

```bash
./run.sh
```

`run.sh` выбирает `.venv/bin/python` или системный Python, добавляет `gui/` в `PYTHONPATH` и запускает локальную PyQt-оболочку. Сам launcher не вызывает `sudo` и не меняет сеть.

Полезные безопасные команды:

```bash
./run.sh --list-presets
./run.sh --list-strategies
./run.sh --build-plan
./run.sh --runtime-contracts
./run.sh --launch-composer-status
./run.sh --strategy-parser-preflight
./run.sh --discord-tunnel-core-preflight --tunnel-core-binary /usr/bin/xray --tunnel-core-kind xray
./run.sh --discord-tunnel-status
./run.sh --discord-tunnel-evidence   # current-run EvidenceGraph / CapabilityVerdict
./run.sh --privileged-executor-status # P02 helper provenance/readiness
./run.sh --runtime-kernel-status       # P02 read-only owned-resource status
```

Полный список CLI:

```bash
./run.sh --help
```

## Что входит в P04d / v0.8 RC4 candidate

Рабочая база включает:

- vendored-ядро `zapret2` и проверяемую карту локальной сборки;
- PyQt GUI с разделами «Обзор», «Ядро», «Пресеты», «Диагностика», «Туннель», «Настройки» и «Логи»;
- модель `пресет -> упорядоченные профили -> filter/range/direction/strategy`;
- каталог стратегий, выбор активной стратегии и экспорт результатов Blockcheck;
- Blockcheck Lab, service targets, проверку покрытия, матрицу наблюдений и универсальный HAR workbench;
- owner-confirmed runtime: workspace-scoped ownership, checked nft batch, reconciliation, plan/hash/confirmation, NFQUEUE и остановку только точно идентифицированного managed `nfqws2`;
- отдельную экспериментальную ветку SOCKS5/VLESS с импортом профиля, внешним core, probes и безопасным запуском Discord через локальный SOCKS;
- typed network truth для tunnel lane: local SOCKS не считается remote/app readiness; evidence привязан к run/config/receipt, а semantic-loss/bypass не могут дать ложный green verdict;
- P02 privilege boundary: GUI остаётся unprivileged; `sudo -A` вызывает только root-owned bounded executor с finite action IDs и confirmed PlanHash; пароль не хранится;
- P04b execution authority: `presetPath -> ImmutableExecutionPlan`; runtime argv и file inputs связаны location-independent Plan hash, а legacy `runtimeArgs` остаётся compatibility-only metadata;
- P04b resource location: explicit root / `ZAP2_RESOURCE_ROOT` / verified checkout fallback; обычный installed package без resource tree fail-closed, полный S-INSTALL packaging ещё не заявлен;
- P04d action authority: все 117 historical selector destinations переводятся в canonical ActionContracts до исполнения; catalog/dispatcher закрыты как 119/119;
- P04d CLI safety: `main()` больше не содержит first-match action branches; contradiction gate и selector-scoped compatibility executor fail-closed;
- P04d generated metadata/projection: compatibility bindings воспроизводимы генератором, а CLI/help/GUI metadata строится из одного ActionContract catalog;
- светлую и тёмную тему с полной семантической привязкой настраиваемых цветов;
- опциональную изолированную security IP blocklist policy с validated last-known-good cache и явным periodic systemd timer.

Подробный текущий статус: `docs/PROJECT_STATUS.md`.

## Что текущая линия не обещает

Версия не означает:

- наличие одного пресета, который всегда одновременно чинит YouTube, Discord и Discord Voice;
- автоматическое объединение любых найденных стратегий в корректный пресет;
- гарантированный результат на другом провайдере или после изменения DPI;
- готовый AUR-пакет, автообновление, автозапуск и полностью управляемый `systemd`-сервис;
- готовую прозрачную маршрутизацию через VLESS/VPN;
- стабильную поддержку Discord Voice.

Историческая граница v0.4 описана в `docs/V04_RELEASE.md`; переходы P01/P02/P03/P04 и правила присвоения версий — в `docs/VERSIONING.md`, `docs/PROJECT_STATUS.md` и `docs/P04_REFORENSICS.md`.

## Основной рабочий цикл

```text
диагностика цели
-> Blockcheck/HAR/наблюдение соединения
-> выбор или экспорт стратегии
-> просмотр runtime plan
-> подтверждение plan id/hash
-> запуск nftables + nfqws2
-> проверка сервиса
-> остановка и откат owned-правил
```

Результат стратегии всегда проверяется на реальной машине владельца. Автотесты подтверждают структуру, парсинг, планы и границы безопасности, но не могут доказать обход конкретного DPI.

## Структура

```text
core/         vendored zapret2 и метаданные импорта

gui/          Python/PyQt приложение

docs/         актуальная документация и записи реализованных этапов

profiles/     локальные контексты и hostlists

presets/      пресеты nfqws2 и их профили

strategies/   каталог стратегий и импортированные варианты

runtime/      контракты runtime lifecycle

tools/        read-only проверки и вспомогательные утилиты

tests/        автономные тесты без изменения сети

meta_tools/   инструменты процесса разработки, включая снимок devctl
```

Подробная карта: `docs/PROJECT_STRUCTURE.md`.

## Безопасность

Проект не должен скрыто:

- устанавливать пакеты или скачивать исполняемые файлы;
- запускать `sudo` без явного действия владельца;
- менять чужие таблицы `nftables`;
- останавливать процессы, PID которых не записан самим приложением;
- печатать VLESS URI, UUID и другие секреты в логи;
- применять внешние Windows-пресеты без перевода на Linux/NFQUEUE модель.

Подробности: `docs/SAFETY_AND_PRIVILEGE_BOUNDARY.md`. Runtime recovery: `docs/RUNTIME_OWNERSHIP_RECOVERY.md`. Security blocklist: `docs/SECURITY_IPBLOCKLIST.md`.

## Документация

Главная точка входа: `docs/README.md`.

Активная проектная документация ведётся на русском языке. Команды, имена опций, идентификаторы, протоколы и названия upstream-проектов сохраняются в оригинальном виде. Документация внутри `core/zapret2/` является vendored upstream и не переводится локально.

Результаты генерального аудита: `docs/DOCUMENTATION_AUDIT.md`.

Текущие недостатки по горизонтальным категориям: `docs/KNOWN_GAPS_CHECKLISTS.md`.

## Проверки

Минимальная локальная проверка:

```bash
python -m pytest -q tests/test_documentation_language.py tests/test_v04_release_documentation.py
python tools/gui_checks/check_project_tree.py
PYTHONPATH=gui python -m zap2_gui.app
```

Полный набор тестов не требует сети, `sudo`, настоящего `nftables` или запуска внешнего tunnel core. Интеграционные проверки реального трафика выполняются владельцем отдельно.

## Разработка через devctl

Изменения проекта применяются devctl-патчами:

```text
patch.zip -> devctl plan -> devctl start
```

Патч обязан содержать корректный `manifest.json`, payload в `files/` и проверки, которые не меняют сетевое состояние машины.


## Tor backends и v2rayNG

C Tor остаётся системным backend, Arti добавлен отдельным managed backend, а применимая VLESS/transport-логика v2rayNG перенесена выборочно. Подробности: `docs/TOR_BACKENDS_AND_V2RAYNG_IMPORT.md`.

### Настройка интерфейса и каталога пресетов

Hot-swap пресетов, portable JSON-темы, `Ctrl+F`-поиск и встроенный strat_collection с консервативным автопортом однозначно совместимых записей описаны в `docs/CUSTOMIZATION.md`.

### Тестовое окружение UserTestSpace

`devctl start` намеренно не зависит от pytest. После успешного применения патча
перейдите в созданный `UserTestSpace/<version>/project` и выполните
`bash meta_tools/uts_prepare.sh`. Скрипт проверит UTS test environment, при
необходимости установит pytest системным package manager на Arch-like системе
или создаст fallback `.uts-venv` рядом с `project/`. Режимы `--p01` и `--full`
запускают regression без pytest cache и Python bytecode.
