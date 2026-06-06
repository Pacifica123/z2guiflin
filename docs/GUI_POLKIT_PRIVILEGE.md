# GUI-запрос прав через sudo askpass

Начиная с `v0.3-beta_stage_12` основной GUI-путь privileged start/stop использует не `pkexec`, а `sudo -A` + `SUDO_ASKPASS`. Причина практическая: на целевой системе `pkexec` успешно показывал графический запрос прав, но запускал `nfqws2` так, что после privilege drop процесс терял возможность создать NFQUEUE и падал на `nfq_create_queue(): Operation not permitted`. Ручной `sudo`-путь при этом уже был рабочим.

Новая цепочка:

```text
PyQt button -> sudo -A -> SUDO_ASKPASS helper -> python -m zap2_gui.app --default-start/--default-stop
```

Пароль не вводится в терминале. GUI создаёт временный executable helper в `.zap2/runtime/askpass/zap2-sudo-askpass`, который запускает `python -m zap2_gui.askpass` и показывает графический диалог. Пароль не сохраняется в `.zap2`, не пишется в runtime logs и не передаётся ассистенту. Он только выводится в stdout askpass-helper по стандартному протоколу `sudo -A`.

## Почему не собственный root-helper

Мы не вводим setuid-бинарник и не ставим постоянный privileged daemon. Runtime остаётся owner-controlled:

1. GUI строит план.
2. GUI сохраняет confirmation для конкретного `planHash`.
3. GUI вызывает `sudo -A` только для уже подтверждённого плана.
4. `default-start` применяет только owned nftables table и запускает session.
5. При падении session выполняется rollback owner-rules.

## Drop identity

GUI больше не форсирует `ZAP2_RUNTIME_DROP_IDENTITY=upstream-default` и не передаёт `--uid=0:0`. Через `sudo -A` используется тот же путь, что и у ручного sudo: `nfqws2` получает `--uid=<SUDO_UID>:<SUDO_GID>` от session runner. Public runtime inputs для hostlist и Lua init-файлов остаются обязательными, чтобы файлы были доступны после `dropcaps()`.
