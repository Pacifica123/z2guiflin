# GUI-запрос прав через polkit

Этот документ фиксирует правило для privileged действий из PyQt GUI: приложение не
просит пароль само, не хранит пароль и не просит вводить `sudo` в терминале после
нажатия кнопки.

Для включения и отключения default workflow GUI использует системный механизм
polkit через `pkexec`:

```text
PyQt button -> pkexec/polkit -> графический authentication agent -> python -m zap2_gui.app --default-start/--default-stop
```

## Что теперь делает GUI

Во вкладке `Обзор` появляются две privileged-кнопки:

```text
Включить через графический запрос прав
Отключить через графический запрос прав
```

Перед запуском кнопка показывает локальное предупреждение, затем вызывает
`pkexec`. Пароль или подтверждение показывает desktop authentication agent
окружения рабочего стола. Приложение не принимает пароль как строку и не передаёт
его в subprocess.

## Что остаётся обязательным

GUI не отменяет lifecycle gate. Перед privileged запуском всё ещё нужны:

```text
1. default-start-plan / default-stop-plan
2. runtime-confirm соответствующего plan id
3. только потом GUI-кнопка privileged start/stop
```

То есть кнопка не является обходным путём вокруг `planHash` и confirmation-файла.
Если plan не сохранён или confirmation устарел, обычный CLI workflow завершится
ошибкой, а GUI покажет эту ошибку в выводе.

## Почему не sudo в терминале

`sudo` из GUI обычно приводит к плохому UX: пользователь нажимает кнопку в окне,
а пароль должен вводить в терминале, из которого приложение было запущено.
Поэтому для GUI-режима выбран `pkexec`/polkit.

`sudo` остаётся допустимым для ручного CLI-сценария разработчика, но GUI-кнопки
privileged start/stop не должны подменять себя терминальным `sudo`.

## Ограничения

Для работы нужен установленный `pkexec` и активный polkit authentication agent в
текущей desktop-сессии. Если agent не запущен, GUI покажет ошибку `pkexec`, но не
будет падать обратно в терминальный ввод пароля.

Патч не добавляет автозапуск, не включает service mode и не смешивает bootstrap с
runtime lifecycle.

## Связь с build workflow

`pkexec` используется только для privileged start/stop. Локальная сборка ядра не
должна запускаться через `sudo` или `pkexec`, иначе build artifacts внутри
workspace могут стать root-owned. Поэтому GUI содержит отдельную кнопку
`Собрать без sudo`, а privileged кнопка `Включить` сначала проверяет наличие
исполняемого `nfqws2` и не вызывает `pkexec`, если бинарник ещё не собран.

После privileged действия GUI показывает read-only статус. Если статус говорит
`not-started`, значит был только plan/confirmation или действие завершилось до
session start. Если статус говорит `started` и `session status: running`, runtime
считается включённым для текущего workspace.


## GUI/pkexec и NFQUEUE capability

В Stage 7 GUI/pkexec временно форсировал `ZAP2_RUNTIME_DROP_IDENTITY=polkit-root`, что добавляло `--uid=0:0` для `nfqws2`. После переноса hostlist и Lua init-файлов в public runtime directory это оказалось лишним и на некоторых системах приводило к `nfq_create_queue(): Operation not permitted`.

Теперь GUI/pkexec start передаёт `ZAP2_RUNTIME_DROP_IDENTITY=upstream-default`: session runner не добавляет явный `--uid`, а оставляет upstream default privilege-drop логику `nfqws2`. GUI по-прежнему не хранит пароль: подтверждение выполняет системный polkit agent.
