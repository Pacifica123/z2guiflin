# Итог патча — P02 owned lifecycle/state + privilege boundary

База: `post_z2flingui_20260923_223616_after_workspace-sync_d00f3e2.zip`, HEAD `d00f3e2` после принятого P01.
План: `P02_RUNTIME_LIFECYCLE_KERNEL.md` из planning-архива с RA meta-invariant: после принятого P01 выполнена повторная форензика, противоречащие текущему HEAD предположения не переносились автоматически.

## Re-forensics / shadow evidence

- P01 принят на реальном UTS: focused P01 и полный regression завершились с exit code `0`.
- Подтверждён P02 blocker: прежний стандартный GUI privilege path запускал writable project Python под root через `sudo -A ... PYTHONPATH=<workspace>/gui ... python -m zap2_gui.app`.
- Выполнен `S-UPSTREAM` без merge. Присланный bol-van candidate archive имеет SHA-256 `769df14fa4463fbe9744a2aab97e7f1bfe1a2f77a669981f4e6372d7b86d71a9`; текущий vendored core заканчивается `0.9.5.3`/`LUA_COMPAT_VER=5`, candidate — `1.0.6`/`LUA_COMPAT_VER=6`. Это подтверждает отдельный P03 semantic-generation switch и не требует переносить migration ядра в P02.

## Что реализовано

- Удалён standard broad-root import GUI package. GUI/CLI остаются unprivileged и делегируют только конечные действия root-owned helper `/usr/local/libexec/zap2-runtime-executor`.
- Helper является standalone stdlib Python (`python3 -I`) и не импортирует `zap2_gui`. Он запрещает опасные env (`PYTHONPATH`, `PYTHONHOME`, `LD_PRELOAD`, `LD_LIBRARY_PATH`, `BASH_ENV`, `ENV`), произвольный shell/argv и произвольный executable.
- Privilege protocol: canonical JSON bytes через stdin + `requestHash`; внутри boundary повторно проверяются exact `PlanHash` и owner confirmation. Поддерживаются только finite action IDs для owned nft observe/check/execute и confirmed `nfqws2` start.
- Start Plan теперь связывает exact runtime bytes: `nfqws2`, Lua, hostlist/strategy/blob inputs, owner uid/gid и NFQUEUE selection. После confirmation mutation входного файла/identity меняет Plan и блокирует execution.
- Helper читает workspace input через symlink-safe path walk, проверяет SHA-256, staging выполняется в root-owned `/run/zap2`; privileged effect строится из уже проверенных bytes.
- Добавлен единый `runtime_kernel_status` с ownership states: `absent | owned-active | owned-stale | owned-partial | foreign-conflict | unknown | migration-required` и `next safe action`.
- `Reconcile` остаётся только для owner-proven mutable resources. Foreign/unknown никогда не auto-delete/repair.
- Composite default start/stop получает общий `runId`; child owner-rules/session receipts сохраняют lineage. Workflow lock сериализует composite action вокруг gap между nft и process lifecycle.
- Legacy live-session schema больше не мигрирует при status-read. Добавлен explicit receipted `MigrationTxn`: detect -> backup -> validate exact process identity -> atomic replace -> receipt. Unknown newer schema fail-closed.
- Read-only status/reconcile/privilege preview действительно не создают `.zap2` и не изменяют workspace. Askpass helper создаётся только непосредственно перед реальным owner-requested execution.
- `service-apply` в P02 честно переведён в plan-only/staged; privileged Discord pre-TLS GUI bridge — staged/unsupported; blockcheck не расширяет standard executor.
- CLI/GUI docs обновлены под bounded executor; старый `sudo ... PYTHONPATH ... zap2_gui.app` оставлен только как явно исторический/запрещённый контекст.
- `meta_tools/uts_prepare.sh --p02` добавляет P02 regression в уже принятую UTS-модель; `devctl start` по-прежнему не зависит от pytest.
- Добавлен dependency-free `tools/check_p02_runtime_lifecycle.py` для devctl: finite-helper contract + outside-checkout read-only lifecycle/privilege smoke без root/pytest/cache/bytecode.

## Verification, выполненный до упаковки

- P02 focused regression после финальных read-only исправлений: PASS.
- Полный repository regression разбит на две группы из 80 test-файлов; обе группы завершены с exit code `0`.
- Коллекция после P02: `474 tests collected`.
- Dependency-free P02 smoke: PASS; не создаёт `.zap2`, pytest cache или bytecode в source tree.
- `S-INSTALL/L3` disposable probe: source helper установлен как `/usr/local/libexec/zap2-runtime-executor`, `root:root`, mode `0755`; installed SHA-256 равен project helper SHA-256 `5cca5a0798c7e1880083f2a9a8c5762203a146d348e886e10052b2190115a697`.
- Installed helper `--self-test`: PASS. Запуск с `PYTHONPATH=/tmp/attacker`: reject, rc=2.
- Outside-checkout `--privileged-executor-status`: `ready`; privilege preview не содержит `zap2_gui.app`/`PYTHONPATH`; runtime-kernel status остаётся read-only и не создаёт `.zap2`.
- В disposable container nft observation классифицирован как `unknown` из-за отсутствия OS network-admin capability; это не повышалось до PASS и не считается L3 firewall mutation evidence.

## Ограничения P02

- P02 не переключает vendored zapret2 core; это P03.
- Реальный nft/NFQUEUE start/stop на машине владельца требует owner L3 run после установки helper; deterministic/container evidence не повышается до live-network/app evidence.
- systemd service execution и privileged Discord diagnostic не входят в standard finite executor этого патча.
