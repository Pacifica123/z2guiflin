# Runner runtime-сессии

`v0.3-alpha_stage_11` вводит первый исполняемый runtime-слой: guarded session runner для локального процесса `nfqws2`.

Это не bootstrap, не installer и не service mode. Runner запускает и останавливает только процесс, который описан default runtime plan, подготовлен через Stage 10 и подтверждён owner confirmation.

## Что делает Stage 11

Stage 11 добавляет команды:

```bash
PYTHONPATH=gui python -m zap2_gui.app --runtime-session-start --profile default
PYTHONPATH=gui python -m zap2_gui.app --runtime-session-status --profile default
PYTHONPATH=gui python -m zap2_gui.app --runtime-session-stop --profile default
```

Перед стартом runner проверяет:

- существует ли подготовленный `runtime-default-manual-local-start-plan`;
- совпадает ли текущий `planHash` с сохранённым планом;
- есть ли owner confirmation для того же `planHash`;
- существует ли `core/zapret2/nfq2/nfqws2`;
- является ли `nfqws2` исполняемым файлом.

Если чего-то не хватает, session не запускается.

## Что записывается в `.zap2/runtime`

Runner использует workspace-only state store:

```text
.zap2/runtime/
  sessions/default.session.json
  sessions/default.nfqws2.args
  sessions/default.nfqws2.pid
  logs/default.nfqws2.stdout.log
  logs/default.nfqws2.stderr.log
  logs/default.nfqws2.debug.log
  logs/default.runtime.jsonl
```

`default.session.json` содержит PID, `planId`, `planHash`, путь к бинарнику, argv, marker владения и safety-флаги.

Обязательный marker:

```text
zap2-runtime-session-v1
```

Без него runner не считает session своей.

## Почему stop безопаснее обычного kill

`--runtime-session-stop` останавливает только PID, который записан в нашем session state. Перед отправкой сигнала runner проверяет:

- что session file имеет наш marker;
- что PID больше 1;
- что процесс жив;
- что `/proc/<pid>/cmdline`, когда доступен, соответствует записанному binary path.

Если PID уже не существует, runner не отправляет сигнал и помечает state как `stale`. Если PID существует, но команда не совпадает с session record, stop отклоняется.

## Чего Stage 11 не делает

Stage 11 не делает следующие вещи:

- не запускает `make`;
- не применяет firewall/routing rules;
- не вызывает `iptables`, `nft`, `ip`, `systemctl`;
- не создаёт и не включает systemd service;
- не вызывает upstream installer scripts;
- не делает remote bootstrap;
- не исправляет систему автоматически.

Сам по себе запущенный `nfqws2` ещё не означает полноценную работу стратегии, потому что трафик ещё не направлен в NFQUEUE. Это появится только в будущих owner-confirmed apply/revert patch.

## Связь со Stage 10

Stage 10 дал `prepare -> confirm -> log`. Stage 11 использует этот gate как обязательное условие запуска процесса.

Минимальный порядок для владельца после локальной сборки ядра:

```bash
PYTHONPATH=gui python -m zap2_gui.app --runtime-prepare start --profile default
PYTHONPATH=gui python -m zap2_gui.app --runtime-confirm runtime-default-manual-local-start-plan
PYTHONPATH=gui python -m zap2_gui.app --runtime-session-start --profile default
PYTHONPATH=gui python -m zap2_gui.app --runtime-session-status --profile default
PYTHONPATH=gui python -m zap2_gui.app --runtime-session-stop --profile default
```

Если plan изменится между confirmation и start, запуск будет отклонён по `planHash`.

## Sudo-owner drop identity

Начиная с `v0.3-beta_stage_3`, runner при root/sudo запуске добавляет в args файл `nfqws2` явный `--uid=<uid>:<gid>`. Приоритет выбора:

1. `SUDO_UID/SUDO_GID`, если команда запущена через `sudo`;
2. владелец корня workspace, если root запустил команду без sudo owner env;
3. `0:0` как диагностический fallback.

Это нужно, потому что upstream `nfqws2` по умолчанию сбрасывает root в UID/GID `2147483647`, а такой synthetic пользователь может не иметь доступа к hostlist и runtime-файлам внутри домашнего workspace владельца.

## Ограничение session runner

Runner запускает процесс с минимальным session config: queue number, pidfile, debug log, drop identity и hostlist path из default profile. Это только lifecycle процесса. Реальное направление трафика, apply/revert системных правил и default start/stop workflow остаются отдельными слоями.

## Использование в default workflow

В Stage 14 session runner вызывается не напрямую, а как часть `default-start/default-stop`. Start workflow проверяет `nfqws2` до применения owner rules, а stop workflow останавливает только recorded PID с marker `zap2-runtime-session-v1` перед revert owner rules.


## Runtime-копии входных файлов

`nfqws2` запускается не напрямую с исходным абсолютным `profiles/hostlists/default.hosts`, а с копией в `.zap2/runtime/session-inputs/`. Это нужно для GUI/polkit-запуска: после `dropcaps()` абсолютный путь через пользовательский workspace может стать недоступен, даже если первичная загрузка hostlist уже прошла. Подробнее: `docs/RUNTIME_SESSION_INPUTS.md`.


## v0.3-beta_stage_9: public hostlist input после dropcaps

GUI/pkexec start использует public runtime copy hostlist под `/tmp/zap2-runtime-inputs/...`, а не `.zap2/runtime/session-inputs/...`. Это нужно, чтобы `nfqws2` мог выполнить повторный `file_open_test` после `dropcaps()`, когда traversal по `/home/<owner>/...` может быть запрещён из-за потери capabilities.

## v0.3-beta_stage_10: public Lua inputs

GUI/pkexec start теперь переписывает `--lua-init=@...` аргументы на public runtime copies под `/tmp/zap2-runtime-inputs/.../lua/`. Это закрывает ошибку:

```text
LUA file '.../core/zapret2/lua/zapret-lib.lua' ... not accessible
I drop my privileges and do not run Lua as root
check file permissions and +x rights on all directories in the path
```

Причина та же, что и у hostlist: после `dropcaps()` `nfqws2` не должен зависеть от traversal по приватному workspace. Vendored Lua остаётся в `core/zapret2/lua/`, а runtime получает per-plan копию с правами `0644`.
