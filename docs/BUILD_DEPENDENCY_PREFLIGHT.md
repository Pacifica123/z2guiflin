# Предварительная проверка зависимостей сборки

`v0.3-beta_stage_2` добавляет read-only проверку системных зависимостей перед локальной сборкой `nfqws2`.

Проблема, которую закрывает этап: `--default-build` мог честно запускать `make`, но при отсутствии системных dev-пакетов владелец видел уже низкоуровневую ошибку компилятора, например отсутствие `libnetfilter_queue/libnetfilter_queue.h`. Это не ошибка runtime workflow, но плохой UX: проект должен заранее сказать, что именно отсутствует и какие пакеты обычно нужны.

## Команда

```bash
PYTHONPATH=gui python -m zap2_gui.app --default-build-deps
```

Команда не запускает `make`, не вызывает `sudo`, не ставит пакеты и не меняет рабочее дерево. Она только проверяет:

- `make`;
- C-компилятор (`cc`, `gcc` или `clang`);
- `pkg-config`/`pkgconf` как recommended helper;
- заголовки `zlib.h`;
- заголовки `libnetfilter_queue`;
- заголовки `libnfnetlink`;
- заголовки `libmnl`;
- LuaJIT или Lua headers.

Если обязательные элементы отсутствуют, отчёт показывает подсказки для Debian/Ubuntu, Fedora/RHEL-like, Arch/Manjaro и openSUSE. Эти команды являются подсказками владельцу, а не действиями приложения.

## Связь с default build

`--default-build-plan` теперь включает секцию `dependency preflight`, но host-specific статус зависимостей не входит в `planHash`. Это важно: если владелец сначала увидел missing dependencies, затем установил пакеты, старый plan не должен ломаться только потому, что состояние системы улучшилось. Hash фиксирует сам план сборки, а preflight остаётся текущей диагностикой.

`--default-build` перед запуском `make` выполняет тот же preflight. Если обязательных зависимостей нет, команда завершается состоянием `blocked`, сохраняет state/log и не запускает `make`. Это лучше, чем состояние `failed` после ошибки компилятора: причина теперь известна до сборки.

## Границы

Preflight не является installer-слоем. Он не запускает:

- `apt`, `dnf`, `pacman`, `zypper`;
- `sudo`;
- upstream scripts вроде `install_easy.sh` или `install_prereq.sh`;
- `make`;
- firewall/service/runtime actions.

Установка build dependencies остаётся локальным действием владельца машины.
