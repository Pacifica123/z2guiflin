# Основной workflow сборки

`v0.3-beta_stage_1` добавляет недостающий мост между local build adapter Stage 6 и реальным `default-start` Stage 14. Теперь отсутствие `core/zapret2/nfq2/nfqws2` не считается тупиком: владелец получает отдельный owner-confirmed путь локальной сборки vendored-ядра.

Это не bootstrap и не installer. Workflow не скачивает исходники, не вызывает `install_easy.sh`, не запускает upstream installer scripts, не трогает `nftables`, не управляет `systemd` и не требует `sudo`. Единственная разрешённая мутация — build artifacts внутри `core/zapret2`.

## Проверка зависимостей сборки

Перед сборкой можно выполнить read-only preflight:

```bash
PYTHONPATH=gui python -m zap2_gui.app --default-build-deps
```

Он проверяет `make`, C-компилятор и dev-заголовки `zlib`, `libnetfilter_queue`, `libnfnetlink`, `libmnl`, LuaJIT/Lua. Если чего-то не хватает, команда показывает подсказки по пакетам, но не запускает `sudo` и не устанавливает ничего автоматически.

`--default-build` теперь сам выполняет этот preflight перед `make`. Если зависимости отсутствуют, результат будет `blocked`, а не compiler-level `failed`: сборка не начнётся, state/log сохранят причину и owner action hints.

## Правильный порядок первого запуска

Сначала проверить зависимости и подготовить план сборки default build target:

```bash
PYTHONPATH=gui python -m zap2_gui.app --default-build-deps
PYTHONPATH=gui python -m zap2_gui.app --default-build-plan
```

Затем подтвердить именно этот plan hash:

```bash
PYTHONPATH=gui python -m zap2_gui.app --runtime-confirm runtime-default-manual-local-default-build-workflow-plan
```

Затем выполнить локальную сборку без `sudo`:

```bash
PYTHONPATH=gui python -m zap2_gui.app --default-build --confirm runtime-default-manual-local-default-build-workflow-plan
```

После успешной сборки нужно заново подготовить и подтвердить start-plan, потому что runtime preflight должен видеть уже существующий исполняемый `nfqws2`:

```bash
PYTHONPATH=gui python -m zap2_gui.app --default-start-plan
PYTHONPATH=gui python -m zap2_gui.app --runtime-confirm runtime-default-manual-local-default-start-workflow-plan
sudo PYTHONPATH=gui python -m zap2_gui.app --default-start --confirm runtime-default-manual-local-default-start-workflow-plan
```

Отключение остаётся прежним:

```bash
PYTHONPATH=gui python -m zap2_gui.app --default-stop-plan
PYTHONPATH=gui python -m zap2_gui.app --runtime-confirm runtime-default-manual-local-default-stop-workflow-plan
sudo PYTHONPATH=gui python -m zap2_gui.app --default-stop --confirm runtime-default-manual-local-default-stop-workflow-plan
```

## Почему build не встроен внутрь sudo start

`default-start` запускается через `sudo`, потому что apply/revert слой управляет owned nftables table. Сборку ядра нельзя автоматически делать внутри этой команды: иначе build artifacts в рабочем дереве могут стать root-owned. Поэтому сборка вынесена в отдельный workflow, который явно отклоняет root/sudo execution по умолчанию.

## Что сохраняется в `.zap2/runtime`

`--default-build-plan` создаёт:

- plan file в `.zap2/runtime/plans/`;
- rollback notes в `.zap2/runtime/rollback/`;
- запись runtime log в `.zap2/runtime/logs/default.runtime.jsonl`;
- plan hash, подтверждаемый обычным `--runtime-confirm`.

`--default-build` после подтверждения создаёт build state в `.zap2/runtime/sessions/default.default-build.json` и пишет результат команд/артефактов в runtime log.

## Границы

Default build workflow не выполняется автоматическими проверками, не требует root, не меняет firewall/service state и не использует сеть. Если локальная система не содержит зависимостей сборки (`zlib`, `libnetfilter_queue`, `libnfnetlink`, `libmnl`, LuaJIT/Lua, `pthread` и toolchain), preflight блокирует `make` до запуска компилятора и показывает подсказки владельцу. Если preflight прошёл, но upstream Makefile всё равно завершился ошибкой, `default-build` сохраняет stderr и artifact status как раньше.
