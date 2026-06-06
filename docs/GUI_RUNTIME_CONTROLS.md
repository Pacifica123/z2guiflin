# GUI runtime controls

`v0.3-beta_stage_4` переносит существующий CLI workflow в PyQt shell. Это не новый executor и не обход confirmation gate. GUI показывает те же действия, которые уже доступны через CLI:

- подготовить план сборки;
- подтвердить план сборки;
- подготовить план запуска;
- подтвердить план запуска;
- показать статус;
- подготовить план отключения;
- подтвердить план отключения;
- показать команды для терминала.

GUI не запускает `sudo` автоматически. Privileged команды остаются терминальными owner-confirmed действиями:

```bash
sudo PYTHONPATH=gui python -m zap2_gui.app --default-start --confirm runtime-default-manual-local-default-start-workflow-plan
sudo PYTHONPATH=gui python -m zap2_gui.app --default-stop --confirm runtime-default-manual-local-default-stop-workflow-plan
```

Такой компромисс нужен, чтобы GUI уже был полезен для управления workflow, но не превращался в скрытый installer или privilege escalation wrapper.

## Статус

Добавлена CLI-команда:

```bash
PYTHONPATH=gui python -m zap2_gui.app --default-status
```

Она читает только workspace state и session state. Команда не вызывает `nft`, `systemctl`, не отправляет сигналы процессам и не исправляет состояние автоматически.

## Вкладка “Обзор”

Вкладка `Обзор` теперь содержит runtime controls вместо пустого placeholder. Кнопки вызывают Python adapter-функции и выводят результат в текстовое поле. Для действий, требующих root, GUI показывает copy-paste команды, которые владелец выполняет сам.
