# Runtime ownership и восстановление

Runtime-ресурсы `nftables` принадлежат не только profile id. Их identity строится из UID владельца, digest канонического workspace и profile id. Поэтому две распакованные копии проекта с одинаковым `default` получают разные таблицы и owner marker.

## Что изменилось

- таблица имеет workspace-scoped имя `zap2_u<uid>_<workspace>_<profile>`;
- внутри таблицы хранится owner marker `zap2-owner:<owner-key>`;
- apply/revert сначала проверяют наличие и marker таблицы;
- неизвестная или legacy-таблица никогда не удаляется по одному совпадению имени;
- apply формируется как один `nft -f` batch и перед исполнением проходит `nft --check -f`;
- один owner lifecycle сериализуется file lock внутри `.zap2/runtime/locks/`;
- точный batch сохраняется в `.zap2/runtime/transactions/` для диагностики;
- JSON state записывается через temporary file + `os.replace`;
- session record хранит boot id, `/proc` starttime, executable и digest argv. PID reuse блокируется связкой boot id + PID + starttime, а cmdline должен совпадать с launch receipt. Если после ожидаемого `--uid` Linux скрывает `/proc/<pid>/exe` из-за non-dumpable privilege drop, runner принимает только дополнительное точное совпадение real/effective/saved/fs UID/GID с записанным `dropIdentity`; при доступном `exe` путь по-прежнему обязан совпасть. Старый record без такой identity считается unknown и PID не получает signal.

## Read-only reconciliation

```bash
./run.sh --runtime-reconcile --profile default
```

Команда ничего не исправляет автоматически. Возможные состояния:

- `clean` — owned table отсутствует;
- `consistent-applied` — saved state и owner marker совпадают;
- `stale-state` — state говорит `applied`, но таблица уже отсутствует;
- `cleanup-required` — доказанно owned table существует без согласованного applied-state;
- `conflict` — table name существует, но owner marker другой;
- `unknown` — факты нельзя безопасно прочитать.

`conflict` и `unknown` не разрешают destructive recovery. Для `cleanup-required` используется обычный owner-confirmed revert:

```bash
./run.sh --runtime-revert-plan --profile default
./run.sh --runtime-confirm <PLAN_ID>
./run.sh --runtime-revert --profile default --confirm <PLAN_ID>
```

Никакого `flush ruleset` и массового удаления `zap2_*` recovery не выполняет.

## Core/Lua provenance

После локальной сборки создаётся `.zap2/runtime/core-build-receipt.json`: digest исходников nfqws2, Lua bundle, binary hash, compat values и известные import metadata. Доказанный mismatch блокирует runtime start. Старый prebuilt без receipt остаётся `unknown`, а не ложно объявляется verified.

## P02 canonical owner state

Единая read-only проекция доступна через:

```bash
PYTHONPATH=gui python -m zap2_gui.app --runtime-kernel-status --profile default
```

Она сводит Plan/Run, nft evidence, session evidence и helper provenance в одно из состояний:
`absent`, `owned-active`, `owned-stale`, `owned-partial`, `foreign-conflict`, `unknown`,
`migration-required`. `foreign-conflict` и `unknown` никогда не вызывают automatic deletion.

Legacy live session больше не мигрирует из read-only status. Используется явная транзакция:

```bash
PYTHONPATH=gui python -m zap2_gui.app --runtime-migrate-state --profile default
```

MigrationTxn делает backup -> exact ownership validation -> atomic replace -> receipt. Более новая
неизвестная schema отвергается без записи.
