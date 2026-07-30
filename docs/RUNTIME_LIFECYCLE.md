# Жизненный цикл runtime

Stage 8 вводит контролируемый runtime lifecycle как язык договоров, а не как запуск. До этого проекта уже есть vendored-core, build map, local build adapter и workspace-профили/стратегии. Теперь нужен слой, который заранее разделяет будущие действия на понятные классы.

## Главный принцип

Runtime lifecycle не должен смешиваться с bootstrap. Bootstrap отвечает за структуру проекта, импорт исходников и подготовку базы. Runtime отвечает за будущую работу уже собранного локального ядра на машине владельца.

Запрещённая смесь:

```text
скачать из интернета -> запустить installer script -> включить service -> считать это runtime lifecycle
```

Правильная модель:

```text
профиль -> стратегия -> runtime plan -> подтверждение владельца -> локальное исполнение -> лог -> rollback/revert
```

## Пять сущностей Stage 8

### Run plan

`run plan` описывает намерение высокого уровня: `start`, `stop`, `status`, будущий service install/remove. Он не обязан знать все детали system rules или процесса, но должен связывать профиль, стратегию, действие и safety flags.

### Apply plan

`apply plan` описывает системные изменения, которые могут понадобиться для работы выбранной стратегии. Это отдельный слой, потому что применение правил и запуск процесса — разные действия с разными рисками и разным откатом.

На Stage 8 apply plan существует только как контракт. Реальные правила будут добавлены отдельным патчем после confirmation gate, логов и rollback notes.

### Session plan

`session plan` описывает будущий lifecycle локального процесса в текущей пользовательской сессии: preflight, start, PID/state, status, stop. Он не должен автоматически устанавливать systemd service.

### Service plan

`service plan` описывает будущий service mode. Он должен оставаться отдельным режимом, потому что service install/start/enable/remove — это другая область ответственности, чем временный session runner.

### Rollback notes

`rollback notes` — обязательная часть любого runtime plan. Они должны быть записаны до исполнения, а не после аварии. Если действие нельзя объяснить и откатить, оно не должно становиться default workflow.

## Boundary Stage 8

Stage 8 разрешает:

- читать runtime-схемы;
- читать example-contracts;
- валидировать структуры plan/event/confirmation;
- показывать CLI-сводку контрактов;
- добавлять документацию и тесты.

Stage 8 запрещает:

- запускать `nfqws2`;
- запускать `make`;
- запускать `sudo`;
- менять firewall/routing/service state;
- выполнять upstream installer scripts;
- использовать `curl`/`wget` как установочный путь;
- писать runtime state как будто действие уже произошло.

## Связь с будущими стадиями

Stage 8 создаёт словарь и контракт. Следующие стадии должны развивать его последовательно:

```text
Stage 9  -> generator default start/stop/status plans: ГОТОВО как plan-only слой
Stage 10 -> state dir, logs и confirmation gate: ГОТОВО
Stage 11 -> session runner процесса: ГОТОВО
Stage 12 -> owner-confirmed apply/revert
Stage 13 -> service plans
Stage 14 -> default start/stop workflow
```

Такой порядок нужен, чтобы к первому реальному запуску уже были понятны границы ответственности, формат логов и условия отката.


## Stage 9 boundary

Stage 9 не расширяет права исполнения. Он только связывает профиль, стратегию, build target, ожидаемый бинарник и runtime sections в один выводимый план. Это означает, что будущий GUI уже сможет показать владельцу “что будет сделано”, но кнопки исполнения по-прежнему должны ждать state dir, confirmation gate и отдельный executor.


## Stage 10: state/log/confirmation

После Stage 9 runtime plan может быть сохранён как workspace state. Stage 10 вводит confirmation gate: owner confirmation создаётся не просто по имени действия, а по конкретному `planHash`. Если содержимое prepared plan изменилось, подтверждение должно считаться недействительным для будущего executor.

Слой остаётся неисполняющим. События `planned` и `confirmed` пишутся в JSONL-журнал, rollback notes сохраняются до исполнения, а session/service/apply действия всё ещё представлены только как данные.


## Stage 11: session runner процесса

Stage 11 переводит `session plan` из чистого контракта в guarded executor для одного процесса `nfqws2`. Executor требует prepared start-plan и confirmation для текущего `planHash`, создаёт args file, запускает процесс, пишет PID/state/log и умеет остановить только записанный PID.

Эта стадия всё ещё не является полноценным default workflow: она не создаёт NFQUEUE rules, не вызывает firewall tooling, не устанавливает service и не делает автозапуск. Её задача — закрыть только process lifecycle, чтобы будущий apply/revert мог подключиться к уже проверенному session boundary.


## Stage 12 и граница apply/revert

`apply plan` теперь имеет первый guarded executor, но он остаётся отдельным от `session plan`. Это значит, что запуск `nfqws2` не создаёт firewall rules сам по себе, а применение системных правил не запускает процесс. Будущий default start workflow должен явно выполнить оба шага: owner-confirmed apply, затем confirmed session start.

`revert plan` должен существовать до полноценного start workflow. Stage 12 фиксирует это через отдельный plan id для `revert` и rollback notes. Revert удаляет только owned markers/rules, созданные apply-слоем, и не должен лечить чужую конфигурацию firewall.

## Stage 13: service mode как отдельный lifecycle

После Stage 13 service plan стал отдельным типом runtime lifecycle. Он описывает systemd unit и команды `systemctl`, но не смешивает это с session runner, apply/revert firewall rules или bootstrap. Service mode может быть подготовлен, подтверждён и частично применён владельцем, но он не является дефолтным способом запуска default strategy.

Ключевое правило Stage 13: service mode существует как отдельная форма runtime, но default start/stop workflow должен появиться позже и сначала пройти через session/apply/revert связку.

## Stage 14: default workflow

Stage 14 вводит composite workflow для дефолтной стратегии. Он объединяет уже существующие layers:

```text
runtime start/stop plan -> confirmation gate -> owner-rules apply/revert -> session runner -> runtime log
```

`default-start` сначала проверяет бинарник `nfqws2`, затем применяет owned nftables rules и только после этого запускает session. `default-stop` останавливает только recorded session PID и выполняет revert owned nftables table.

Default workflow остаётся session mode, а не service mode. Systemd service plans Stage 13 существуют отдельно и не используются по умолчанию.
