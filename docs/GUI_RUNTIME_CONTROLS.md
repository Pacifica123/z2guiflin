# Элементы управления runtime в GUI

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
## Графический запрос прав

Privileged кнопки запуска и отключения default workflow теперь должны использовать `sudo -A`/SUDO_ASKPASS. Пароль запрашивает системное графическое окно desktop-сессии, а не терминальный `sudo`. Подробности: `docs/GUI_POLKIT_PRIVILEGE.md`.

## v0.3-beta_stage_6: понятный GUI workflow

Stage 6 исправляет UX-проблему Stage 5: раньше во вкладке `Обзор` можно было
сделать `План сборки` и `Подтвердить сборку`, но не было отдельной кнопки
`Собрать без sudo`. Из-за этого пользователь мог перейти к `Включить` и получить
ошибку про отсутствующий `nfqws2`, хотя визуально казалось, что сборочный workflow
уже пройден.

Теперь GUI показывает полный порядок:

```text
Проверить зависимости -> План сборки -> Подтвердить сборку -> Собрать без sudo
-> План запуска -> Подтвердить запуск -> Включить через графический запрос прав
```

После сборки, включения или отключения GUI автоматически добавляет read-only
статус default workflow. Цель — чтобы пользователь сразу видел, находится проект
в состоянии `started`, `stopped`, `not-started` или `stale`, а не гадал по
последнему выводу `sudo -A`.

Если бинарник `core/zapret2/nfq2/nfqws2` отсутствует или не исполняемый, GUI не
запускает `sudo -A` и показывает штатную последовательность действий для сборки.
Это предотвращает ситуацию, когда графический запрос прав уже прошёл, а runtime
падает на очевидном локальном preflight.


## v0.3-beta stage 7: toggle-first UX

Основной путь в GUI теперь должен идти через одну кнопку `Включить Default` / `Выключить Default`. Она агрегирует подготовку планов, подтверждения и privileged start/stop через sudo askpass, а подробный результат отправляет в основной вывод и вкладку `Логи`. Старые отдельные кнопки остаются как диагностический/developer fallback.

## v0.4-alpha Stage 7z: launch composer

Вкладка `Обзор` теперь получает отдельную панель `Комбинированный запуск`. Она нужна для сценария, где владелец хочет быстро выбрать состав эксперимента:

```text
[x] Zapret default      supported, требует GUI sudo-askpass
[ ] VLESS tunnel        supported, user-space external core
[ ] SOCKS5 upstream     planned placeholder
[ ] MTProto             planned placeholder
[ ] Custom              planned placeholder
```

Кнопки панели разделены по смыслу:

```text
Статус выбранного       read-only snapshot всех компонентов
План выбранного         порядок запуска/остановки и readiness без исполнения
Запустить выбранное     только supported components, в порядке composer
Остановить выбранное    supported components в обратном порядке
```

`zapret-default` продолжает использовать существующий workflow: plan -> confirmation -> `sudo -A/SUDO_ASKPASS`. `tunnel-vless` продолжает использовать `.zap2/tunnel`: plan -> confirmation -> внешний core PID, без sudo и без firewall/service mutation.

Комбинация `zapret-default + tunnel-vless` теперь разрешена только через явный composer-сценарий. Это сделано намеренно: старый tunnel-only путь остаётся чистым экспериментом и по умолчанию не стартует, если Zapret уже running. Composer же показывает предупреждение, запускает Zapret первым, затем tunnel с явным parallel flag, а останавливает в обратном порядке.
