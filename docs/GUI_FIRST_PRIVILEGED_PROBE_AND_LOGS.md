# GUI-first: privileged probe и разделение логов обзора

Дата: 2026-06-29

## Зачем

После перевода Overview в таблицу стало видно две проблемы.

Первая: Discord guided probe из GUI мог видеть, что workflow запущен, но падал на чтении `nft` counters с `Operation not permitted`. Это не ошибка стратегии и не ошибка NFQUEUE. Это недостаток GUI-path: проверка запускалась без прав, хотя чтение counters требует повышенных прав.

Вторая: нижний текстовый dump в Overview снова превращал главный экран в консольную простыню. Для user-mode Overview должен оставаться таблицей, кнопками и коротким статусом. Подробный вывод действий должен жить во вкладке «Логи».

## Что изменено

### Privileged Discord probe

Кнопка `Проверить Discord` теперь вызывает read-only probe через тот же GUI sudo-askpass подход, который уже используется для start/stop workflow.

Команда запускается как:

```text
sudo -A env PYTHONPATH=<workspace>/gui ZAP2_GUI_PRIVILEGE_BRIDGE=sudo-askpass python -m zap2_gui.app --runtime-discord-pretls-guided-probe --profile default --pretls-probe-no-wait --pretls-probe-wait-seconds 30
```

Свойства:

- терминальный ввод пароля не используется;
- пароль не сохраняется;
- firewall и сервисы не меняются;
- probe только читает runtime state, nft counters, состояние `nfqws2`, логи и endpoint snapshots;
- GUI заранее предупреждает пользователя открыть Discord во время 30-секундного окна.

### Overview без старого текстового вывода

Из Overview убран нижний `QPlainTextEdit` с подробным выводом. Теперь Overview показывает:

- таблицу состояния;
- основную кнопку start/stop;
- кнопку privileged Discord probe;
- кнопки копирования таблицы и последнего подробного вывода;
- Developer mode с ручными деталями.

Подробный вывод каждого действия сохраняется в:

```text
.zap2/runtime/logs/default.overview-action-output.log
```

### Logs tab

Вкладка «Логи» теперь имеет две под-вкладки:

- `Overview actions` — последний подробный вывод действия из Overview;
- `Runtime` — обычные runtime events/stdout/stderr/debug tails.

Есть кнопка `Копировать текущую вкладку`, чтобы длинный текст всё ещё можно было передать в чат или issue.

## User-mode контракт

В обычном режиме пользователь не видит plan id, nft commands, `grep`, `pgrep` и raw shell-инструкции. Они остаются только в Developer mode или CLI fallback.
