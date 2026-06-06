# Runtime session inputs

Начиная с `v0.3-beta_stage_8` session runner больше не передаёт `nfqws2` исходный абсолютный путь к `profiles/hostlists/default.hosts`.

Причина: `nfqws2` после открытия NFQUEUE и загрузки первичных данных выполняет `dropcaps()` и повторно проверяет доступ к hostlist. В GUI/polkit-сценарии процесс может остаться `UID=0`, но уже без `CAP_DAC_OVERRIDE`, поэтому абсолютный путь через пользовательский home/workspace иногда становится недоступен даже после успешной первичной загрузки.

Теперь перед запуском создаётся runtime-копия hostlist:

```text
.zap2/runtime/session-inputs/default.hostlist-0.hosts
```

В args-файл `nfqws2` попадает относительный путь:

```text
--hostlist=.zap2/runtime/session-inputs/default.hostlist-0.hosts
```

Это даёт три эффекта:

1. GUI/pkexec start не зависит от прав исходного hostlist-файла.
2. `nfqws2` повторно проверяет уже подготовленный runtime input.
3. Источник `profiles/hostlists/default.hosts` остаётся owner-maintained, а runtime session работает с копией конкретного запуска.

Ограничения:

- копия создаётся только внутри workspace runtime state;
- service/firewall/bootstrap не смешиваются с этим механизмом;
- источник hostlist всё равно остаётся главным файлом профиля;
- после изменения hostlist нужно заново подготовить и подтвердить start workflow.
