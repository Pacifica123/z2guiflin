# Runtime service plans

Stage 13 добавляет **service mode** как отдельный режим controlled runtime lifecycle. Он нужен не для замены session runner, а для будущего сценария, где владелец осознанно устанавливает systemd unit и управляет им как отдельной runtime-формой.

## Что появилось

В проект добавлен adapter:

```text
 gui/zap2_gui/adapters/runtime_service.py
```

Он умеет строить и сохранять service plans для четырёх действий:

```text
install
start
stop
remove
```

CLI:

```bash
PYTHONPATH=gui python -m zap2_gui.app --service-plan install --profile default
PYTHONPATH=gui python -m zap2_gui.app --service-plan start --profile default
PYTHONPATH=gui python -m zap2_gui.app --service-plan stop --profile default
PYTHONPATH=gui python -m zap2_gui.app --service-plan remove --profile default
```

`--service-plan` сохраняет план в `.zap2/runtime/plans/`, создаёт rollback notes в `.zap2/runtime/rollback/` и пишет событие в runtime log. Сам service при этом не устанавливается, не запускается и не останавливается.

## Подтверждение

Service plan подтверждается тем же confirmation gate, что был введён в Stage 10:

```bash
PYTHONPATH=gui python -m zap2_gui.app --runtime-confirm runtime-default-manual-local-service-install-plan
```

Подтверждение привязано к `planHash`. Если unit content, путь workspace, профиль, стратегия или service-dir изменятся, подтверждение устареет.

## Guarded execution

Stage 13 разрешает guarded execution только для:

```text
install
remove
```

Команды:

```bash
sudo PYTHONPATH=gui python -m zap2_gui.app --service-apply install --profile default --confirm runtime-default-manual-local-service-install-plan
sudo PYTHONPATH=gui python -m zap2_gui.app --service-apply remove --profile default --confirm runtime-default-manual-local-service-remove-plan
```

`start` и `stop` пока остаются plan-only. Это сделано намеренно: default runtime workflow для одиночной разработки должен сначала пройти через session mode, apply/revert и только потом получать service start/stop как полноценный режим.

## Что делает install plan

Install plan готовит:

- systemd unit `zap2-default.service`;
- workspace args-file для `nfqws2`;
- `systemctl daemon-reload` как owner-confirmed команду;
- rollback notes, которые указывают на remove plan.

Install plan **не делает**:

- `systemctl enable`;
- `systemctl start`;
- apply/revert firewall rules;
- nftables mutation;
- upstream bootstrap;
- remote install;
- запуск `install_easy.sh`.

## Что делает remove plan

Remove plan должен удалить только unit-файл, созданный Zap2 service plan, и выполнить `systemctl daemon-reload`. Он может попытаться `stop`/`disable`, но не удаляет runtime logs и не трогает firewall rules.

## Почему service mode не дефолт

Service mode удобен позже, когда стратегия уже стабилизирована. На текущем этапе безопаснее и понятнее держать default workflow вокруг session runner: владелец видит процесс, state, PID, logs и может остановить только тот процесс, который записал runtime state.

Поэтому Stage 13 фиксирует правило:

```text
service mode exists, but is not default workflow
```

## Граница проверок

Автоматические проверки могут создавать временную service-dir и fake runner. Они не вызывают настоящий `systemctl`, не пишут в `/etc/systemd/system`, не требуют root и не меняют сервисы машины.
