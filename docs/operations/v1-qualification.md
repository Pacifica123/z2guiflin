> Историческая процедура P07. Владелец закрыл v1.0 01.10.2026; текущая версия 1.1.0. Этот документ сохраняет прежние критерии и область доказательств, а не утверждает, что v1.0 снова открыта. Для текущих изменений см. [контракт v1.1](../developer/V11_PATCH_CONTRACT.md).

# Квалификация v1: порядок действий и честные блокеры

Кандидат 1.0.0rc7 не является final 1.0.0. Прочитайте [PC](../developer/P07_PATCH_CONTRACT.md), [SA](../developer/P07_SPEC_AMENDMENTS.md), [gates/journeys](../generated/qualification.md) и текущий [статус](../PROJECT_STATUS.md) перед выполнением owner проверок. Scope задан в [p07-contract.json](../developer/p07-contract.json); его не меняют молча ради зелёного результата.

## Единая приёмка

Запустите `bash meta_tools/hyperpatch_acceptance.sh --p07` от обычного owner в applied project. Pytest и PyQt6 должны быть доступны выбранному Python. Runner запускает deterministic checks в isolated copies, ограничивает время и owned child process groups, сохраняет полные logs/JUnit/qualification.json/summary.json и ZIP. Root/network/native package mutation сам runner не выполняет. В режиме --p07 exit отражает проверки кандидата: полный regression FAIL или ошибка freeze/проекций запрещает применение; отсутствие owner receipts сохраняет qualification BLOCKED, но позволяет применить RC. Для финальной квалификации выполните `bash meta_tools/hyperpatch_acceptance.sh --p07-release`: тот же pipeline требует все MUST partitions, иначе exit ненулевой.

Локальный успех тестов означает только L0–L2. PrivilegedOS (L3), liveNetwork (L4), targetApp (L5), native package lifecycle и migration/provenance подтверждаются отдельными наблюдениями на выбранной disposable owner машине. Исторические P04d/P05/P06 receipts и исходный контейнерный FAIL не переносятся на current candidate как PASS. Несовпадение PID namespace и /proc требует повторного полного прогона на обычном Linux host.

## Нативный lifecycle и сценарии

Используйте сохранённый P06 пакет 0.10.0rc6 как реальный predecessor, новый 1.0.0rc7 package и [VM recorder](../../meta_tools/p06_vm_acceptance.sh): `bash meta_tools/p06_vm_acceptance.sh --allow-system-install OLD_PACKAGE NEW_PACKAGE EVIDENCE_DIR`. Он запускает установленный /usr/bin/zap2-gui вне checkout и проверяет upgrade receipts/backup/preservation/uninstall; runtime/GUI observations записываются после фактической проверки. Не выдавайте stageDESTDIR fixture за системную установку.

J1/J2: install→GUI→inspect/plan→owner-confirmed build/start→status→stop/revert/exit; helper root-owned/mode/hash, неизменяемый Plan/hash и provenance. J3: в disposable VM внесите воспроизводимый crash на согласованном cutpoint, перезапустите и подтвердите ownership/reconcile, сохранность foreign process/table/file и ограниченное завершение. J5: диагностическое действие должно менять только явно обещанный evidence output, без скрытого persistent/system эффекта. J6: RU/EN/technical query→help→pre/effect→safe action. J7: настоящий P06→P07 upgrade, backup/receipt, сохранение intended normalized capability и пользовательских данных; неизвестный newer/downgrade остаётся non-destructive failure.

J4 допускает supported launch или объявленную bounded failure с next experiment. Однако такой failure не закрывает G02: нужен хотя бы один current owner live VLESS lane с PASS sourceReceipt/fidelity/coreValidate/targetTls/targetHttp. Frozen qualification target lane — Xray TCP/TLS на Arch-like Linux; другие transports/security/core combinations остаются вне подтверждённой supported cell. Чтобы квалифицировать иной lane, требуется SA/profile change, новый freeze и повторная привязка evidence, а не изменение одного PASS слова.

Vesktop aggregate требует current updates.discord.com HTTP, discord.com HTTP, Gateway WebSocket и Electron navigation, с версиями app/core и run/config/connection binding. HTTP-only, bypass и local SOCKS не закрывают G03/G18. Voice/media оцениваются отдельно и не обещаются как supported bootstrap.

## Внешний owner evidence bundle

Путь к JSON передаётся как `ZAP2_P07_OWNER_BUNDLE=/absolute/path/bundle.json` при едином `--p07-release` запуске. Bundle schemaVersion=1, records — массив typed claims. Каждый record содержит claimId (G01..G21/J1..J7), partition, result, binding из candidate-freeze, createdAt/expiresAt (timezone обязательна, окно ≤30 дней), producer, method, environment, scope, limits и artifacts с безопасным относительным path и SHA256. Artifact находится рядом с bundle либо ниже; symlink/traversal/изменённый hash запрещены. Secrets/raw source URI не включайте в общий индекс; закрытые owner artifacts хранят отдельно и передают reviewer осознанно.

Binding содержит candidateVersion, candidateDigest, releaseDigest, pcSha256, profileSha256. Его можно увидеть в runtime/p07/candidate-freeze.json или итоговом qualification.json. Любое изменение исходников/tests/profile/PC/release recipe требует нового freeze и новых receipts; сведения другого snapshot/окна/среды не считаются текущими. Final review partition требует reviewer, отличного от producer. Receipts — локальные attestations: проверка hash не является криптографической гарантией правдивости наблюдений.

Live PASS records содержат predicates sourceReceipt/semanticFidelity/coreValidate/targetTls/targetHttp и scope с runId/coreVersion/configHash/connectionReceiptId/core/transport/security. TargetApp PASS records содержат updatesHttp/discordHttp/gatewayWebsocket/electronNavigation и appVersion/runId. J4 bounded-failure branch содержит nextExperiment и current identity; его не принимают как G02 supported lane. FAIL не исчезает при добавлении другой PASS записи. Invalid bundle не создаёт разрешение на promotion.

## Review и final

Сделайте deliberate failure, экспортируйте redacted support и дайте отдельному assessor оценить: можно ли определить Plan/Run, слой failure, ownership, следующее ограниченное действие; нет ли credentials/source URI/raw config/logs. Для G19 нужен такой artifact и независимая actionability/redaction review, не только unit secret scan. G21 reviewer читает PC→diff→raw evidence→SA до narrative. Все 21 gates и 7 journeys должны быть PASS; ни один resolvable_blocking не скрывают. Только после этого принимают product transition, присваивают 1.0.0/tag отдельным reviewable изменением и архивируют финальные receipts.

До применения devctl-патча новый commit не существует: PRE freeze содержит candidateCommit=null и честный source snapshot digest. G21 review receipt должен указать фактический candidateCommit (полный Git SHA) и привязанный diff/source inventory после применения. Самодельный commit ID не создаётся. Такая PRE запись не закрывает review gate.
