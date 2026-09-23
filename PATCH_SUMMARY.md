# Итог патча — P01 network truth / VLESS / Vesktop

База: `post_z2flingui_20260923_143044_after_runtime-vless-vesktop-recovery-v2_a1bf6c8(1).zip`.
План: `P01_NETWORK_TRUTH_VLESS_VESKTOP.md` из `TGN_z2flingui_v1_planning_NEURALESE_20260923.zip` с учётом RA-правила: план является проверяемой гипотезой, а противоречащие текущему коду и evidence предположения не считаются авторитетными.

## Что реализовано

- Скалярное «ready» для tunnel lane больше не используется как доказательство работоспособности маршрута. Добавлены `ProbeSpan/v1`, `EvidenceGraph/v1` и `CapabilityVerdict/v1`.
- Evidence текущего запуска жёстко связано с `runId`, `connectionId`, `connectionReceiptId`, `configHash` и `coreIdentityHash`. Несовпадение любой привязки не позволяет использовать старый PASS и оставляет capability в `UNKNOWN`.
- В `ProbeSpan` добавлен типизированный `failureClass`: отдельно различаются ошибки process/listener/SOCKS, TLS EOF/reset, TLS timeout, TLS validation, HTTP и application/navigation.
- Добавлен `ConnectionReceipt/v2`: хранится hash исходного URI, normalized hash, список известных и неизвестных query keys, redacted semantic summary, `sourceSemanticHash`, `generatedSemanticHash` и `semanticDiff`. Сам `vless://` URI и UUID в support receipt не записываются.
- Поддержка генератора теперь имеет состояния `SUPPORTED/full`, `EXPERIMENTAL/partial` и `UNSUPPORTED/loss`. Для `SUPPORTED` каноническая семантика source и generated config должна совпасть; распознанная обязательная потеря блокирует запуск.
- Повторяющиеся VLESS query keys отклоняются вместо тихого схлопывания в `dict`. Некорректные bool/int значения и известные, но не представимые значения (например неподдерживаемый `grpc mode`) не могут получить full-support.
- Xray и V2Ray остаются разными capability lanes. `CoreCapability` фиксирует kind, binary hash, identity hash, config hash, config-test status и заявленную область transport/security/fields.
- Сетевые проверки разделены на `socks_method`, `socks_connect`, `target_tls`, `target_http`. PASS локального listener/SOCKS не повышает remote HTTPS или Vesktop capability.
- Любой явно проверенный HTTPS target, включая neutral/control host, получает собственный route verdict. Neutral PASS не засчитывается как Discord/Vesktop PASS.
- Vesktop bootstrap является агрегатом обязательных HTTP routes, Gateway WebSocket и main-window navigation. Пока нет всех current-run predicates, итог остаётся `UNKNOWN` или `UNSUPPORTED`.
- `--discord-launch-allow-failed-preflight` остаётся только owner override действия: `bypassChangesVerdict=false`; bypass не делает capability зелёным.
- SOCKS containment записывается явно: loopback bind, `noauth`, UDP off, доступ приложения только через явные proxy env/Chromium flags; случайный порт не считается authentication.
- Добавлены CLI `--discord-tunnel-evidence` и GUI-действие `Evidence / capability`, где показываются current-run spans, failed/missing predicates, failure classes и следующий полезный эксперимент.
- Route diagnosis сохраняет прежние log-эвристики только как diagnostic hints и отдельно помечает typed EvidenceGraph как источник capability truth.
- Документация P01 описывает границы доказательств, semantic fidelity, containment, neutral-vs-Discord эксперимент и условия, при которых Vesktop нельзя объявлять поддержанным.

## Исправленный devctl / UserTestSpace контракт

- `devctl start` больше не имеет обязательного check, импортирующего pytest. Его P01-gates — только dependency-free AST/smoke/shell-syntax проверки на базовом окружении devctl.
- `pytest` перенесён туда, где он действительно нужен: в post-patch `UserTestSpace/<version>/project`.
- Добавлен `meta_tools/uts_prepare.sh`. Он проверяет Python >= 3.10 и наличие pytest; на Arch-like системе при отсутствии pytest сначала пытается установить `python-pytest` через `pacman`, а если это невозможно — использует отдельный fallback `UserTestSpace/<version>/.uts-venv` и pip.
- `--check` делает только preflight без установки; `--p01`, `--full` и `--pytest ...` запускают regression через подготовленный test runner.
- Pytest всегда запускается с `PYTHONDONTWRITEBYTECODE=1` и `-p no:cacheprovider`; generated `__pycache__`, `.pytest_cache`, `*.pyc`, `*.pyo` внутри UTS project очищаются до/после тестового запуска.
- Venv, если он понадобился, находится рядом с `project/`, а не внутри него, поэтому не загрязняет project diff/post archive.

## Проверки, которые действительно выполнены

- Dependency-free P01 runtime/VLESS/Vesktop smoke: PASS, 5 групп.
- AST parse изменённых Python-модулей: PASS.
- `bash -n meta_tools/uts_prepare.sh`: PASS.
- `meta_tools/uts_prepare.sh --p01`: PASS на pytest 9.0.2.
- Полный repository regression после добавления metatools-скрипта разделён на две группы из 79 test-файлов; обе группы PASS.
- Коллекция: 460 тестов в 79 test-файлах.
- Отдельно проверен host Python без pytest: `--check` корректно сообщает `MISSING/NOT READY` и ничего не устанавливает.
- В используемой среде не было доступного package index/pacman, поэтому ветка фактической сетевой установки `python-pytest`/pip не выдаётся за выполненную; проверены её условия, команды и fail-closed поведение.
- Packaging hygiene: `.zap2/`, `.pytest_cache/`, `__pycache__/`, `*.pyc`, `*.pyo`, build/dist/coverage и локальное runtime state запрещены в patch/post archive.

## Что намеренно не утверждается

Offline fixtures уровня L0–L2 не доказывают, что конкретный пользовательский VLESS server/network сейчас пропускает Discord/Vesktop. В этой среде не было owner/live E1–E8 evidence уровня L4/L5, поэтому P01 не объявляет реальный Vesktop route поддержанным без current-run Gateway WebSocket и main-window evidence.

Persistent Chromium netlog по умолчанию не включён: P01 не создаёт постоянный чувствительный debug trace. Если он понадобится для owner experiment, это должен быть отдельный временный сбор с redaction/cleanup, а не скрытый источник «зелёного» статуса.
