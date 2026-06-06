# Runtime session inputs

Начиная с `v0.3-beta_stage_9` session runner больше не передаёт `nfqws2` ни исходный абсолютный путь к `profiles/hostlists/default.hosts`, ни runtime-копию внутри `.zap2` как основной hostlist path.

## Почему Stage 8 был недостаточен

В `v0.3-beta_stage_8` hostlist копировался в `.zap2/runtime/session-inputs/` и передавался как относительный путь. Это убрало зависимость от исходного файла профиля, но не решило проблему полностью: вся `.zap2`-директория всё равно лежит под пользовательским workspace, например внутри `/home/<owner>/...`.

`nfqws2` после открытия NFQUEUE и первичной загрузки данных выполняет `dropcaps()` и повторно проверяет доступ к hostlist. После сброса capabilities процесс может остаться `UID=0`, но уже без `CAP_DAC_OVERRIDE`; в таком состоянии он может потерять возможность проходить приватные родительские директории пользовательского home/workspace. Поэтому повторная проверка могла падать так:

```text
Loaded 35 hosts ...
Running as UID=0 GID=0
file_open_test: Permission denied
cannot access hostlist file '.../.zap2/runtime/session-inputs/default.hostlist-0.hosts'
```

## Текущий механизм

Перед запуском создаётся per-plan public runtime copy под tmp-like директорией:

```text
/tmp/zap2-runtime-inputs/default-<plan-hash-prefix>/default.hostlist-0.hosts
```

В args-файл `nfqws2` попадает абсолютный путь к этой public runtime copy:

```text
--hostlist=/tmp/zap2-runtime-inputs/default-<hash>/default.hostlist-0.hosts
```

Права выставляются так, чтобы процесс после `dropcaps()` мог пройти директории и прочитать hostlist:

```text
directories: 0755
hostlist:    0644
```

## Что это даёт

1. GUI/pkexec start не зависит от прав исходного hostlist-файла.
2. Повторный `file_open_test` после `dropcaps()` больше не зависит от traversal по `/home/<owner>/...`.
3. Источник `profiles/hostlists/default.hosts` остаётся owner-maintained.
4. Runtime session работает с копией конкретного confirmed plan.
5. Stop делает best-effort cleanup public runtime copy.

## Ограничения

- hostlist не считается секретом в текущем single-owner workflow;
- механизм не запускает service mode и не смешивается с bootstrap;
- после изменения hostlist нужно заново подготовить и подтвердить start workflow;
- если start упал до cleanup, public copy может остаться для диагностики и будет перезаписана следующим запуском того же plan hash.
