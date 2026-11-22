# Архитектура distribution и проверок P06

P06 использует compatibility workspace, чтобы не переписать доказанные P02/P04 семантики путей, Plan и runtime provenance. Immutable package tree находится в `/usr/share/zap2gui`, исполняемый GUI-код — в `/usr/lib/zap2gui/python`, helper — в `/usr/lib/zap2gui`. Пользовательская копия ресурсов и writable build/runtime данные лежат отдельно под XDG_DATA_HOME. Это осознанное копирование с receipt и conflict gate; user workspace не объявляется immutable package tree.

`packaging/build_release.py` использует явный allowlist конкретных файлов и denylist runtime/cache/secrets/native artifacts. Добавление нового импортируемого Python-модуля в `gui/zap2_gui` требует одновременного добавления пути в `packaging/release-files.json`; релизный тест сравнивает полный список Python-модулей с allowlist и проверяет пакет после stage install. Manifest содержит SHA-256 и mode каждой записи; tar/gzip фиксируют порядок, uid/gid, mode и mtime=0. Ни timestamp, ни абсолютный checkout path в release digest не входят. Helper, launcher, desktop entry и обе MIT license notices включены. PKGBUILD привязан к SHA-256 конкретного локального release input. Пакет не включает tests, devctl bundle, текущие runtime captures или compiled core.

`generate_p06_reference.py` выводит справочник из ActionContracts, legacy operand bindings, canonical concepts, runtime schemas, P01 mandatory targets и P03 provenance. `--check` обнаруживает drift. Исторические документы перенесены в `docs/history/stages`; их SHA-256 совпадают с PRE, старые пути содержат явные redirects. Current-help и novice guides не ссылаются на stage archaeology как основной путь.

Единая deterministic приёмка: `bash meta_tools/hyperpatch_acceptance.sh --p06`. Она проверяет reference freshness/links/history, reproducibility/allowlist, staged installed launch вне checkout, workspace upgrade/uninstall ownership, support secret scan, P03 identity и полный isolated regression. Это не clean-VM native start/stop и не внешний network verdict.

Отдельная owner-VM приёмка выполняется через `meta_tools/p06_vm_acceptance.sh` в подготовленной чистой Arch-like VM. Она реально устанавливает пакет и записывает ручную проверку bounded owned lifecycle через установленный GUI. Не запускайте её на рабочей системе без намерения установить пакет. Окончательное принятие RC6 и final SemVer требуют её evidence и задач новичка; история P05 не переписывается без отдельного owner receipt.

[Reference](../generated/reference.md) · [История](../history/README.md) · [Upstream](../upstream/README.md).

Чистая VM: сначала соберите два различных package release через makepkg. Запустите `bash meta_tools/p06_vm_acceptance.sh --allow-system-install OLD_PACKAGE NEW_PACKAGE EVIDENCE_DIR` от обычного владельца. Скрипт устанавливает пакеты, запускает именно установленный launcher вне checkout, проверяет receipts и сохранение данных, записывает ручные подтверждения GUI/runtime/диагностики, экспортирует support и удаляет пакет. Ответ PASS вводят только после фактического наблюдения; отсутствие отдельного прежнего package release означает NOT_RUN для настоящего upgrade, а не успешную повторную установку.

Текущий workflow — `--v11`; `--p07`/`--p07-release` сохранены для исторического P07; предыдущий `--p06` сохраняется как профиль своего этапа. P07 freeze включает shipping source и весь test corpus, PC/profile digests и release digest. Per-test JUnit позволяет видеть локальные FAIL/NOT_RUN для каждого probe; real OS/live/app/package/migration/review требуют внешних typed receipts. Recipe и release manifest воспроизводимы; final version/tag не создаются автоматически.

Авторский package workflow: bash meta_tools/build_local_package.sh создаёт archive/PKGBUILD из checkout в dist/arch/1.5.2; makepkg -si запускают в этом output directory. Предварительная внешняя публикация/сертификация архива не требуется.

### YouTube Blockcheck presets and zero-observation guard (v1.5.2)

`models/service_targets.py` defines `youtube-basic` as static default and `youtube-googlevideo-auto` as an opt-in variant with a dynamic `googlevideo-node` phase. Their static targets and phase ordering remain the same. The GUI checks `service_target_dynamic_phases()` before starting any discovery/CDP. `adapters/blockcheck_gui.py::diagnose_unscanned_candidate` distinguishes an upstream attempt from a pre-strategy failure. In phase-gated runs, a failed DNS gate/sudo/startup or a zero-evidence exit terminates the tournament without treating it as a failed bypass candidate. Raw evidence remains in the candidate log; GUI only shows predefined safe diagnostic codes. No privileged operation or hostlist mutation is introduced.

### P1/P2 GoogleVideo discovery (v1.5.0)

`adapters/googlevideo_node.py` собирает кандидатов с фиксированных YouTube/redirector endpoints,
делает ограниченную DNS-проверку без TCP/TLS и отдаёт только нормализованные имена.
`adapters/googlevideo_cdp.py` опционально запускает отдельный Chromium (POSIX spawn,
`--remote-debugging-pipe`, fd 3/4, временный 0700-профиль) и наблюдает Network CDP-события
без сохранения HAR, URL или cookies. GUI управляет сеансом в `qt_background.py` через
ограничение 120 секунд и явное завершение; CDP не имеет привилегий root.
В `widgets/blockcheck_lab.py` одноразовые браузерные имена проходят повторную проверку и
дополняются P1 fallback, затем попадают в фазу `video` перед штатным redirector.
Проверка CDN-имени и DNS не доказывает работоспособность видеопотока. CDP не подключается
к браузерному профилю пользователя или открытому TCP-порту.
