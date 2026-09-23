> **P02 update (2026-09-23):** описанный ниже broad-root `sudo -A ... PYTHONPATH=<workspace>` путь является историческим Stage 7 поведением и больше не поддерживается. P02 оставляет privileged Discord probe staged/unsupported, пока для него не появится отдельный finite executor action. Standard start/stop использует root-owned bounded executor и не импортирует GUI как root.

# GUI-first: privileged probe и разделение логов обзора

Дата: 2026-06-29

## Зачем

После перевода Overview в таблицу стало видно две проблемы.

Первая: Discord guided probe из GUI мог видеть, что workflow запущен, но падал на чтении `nft` counters с `Operation not permitted`. Это не ошибка стратегии и не ошибка NFQUEUE. Это недостаток GUI-path: проверка запускалась без прав, хотя чтение counters требует повышенных прав.

Вторая: нижний текстовый dump в Overview снова превращал главный экран в консольную простыню. Для user-mode Overview должен оставаться таблицей, кнопками и коротким статусом. Подробный вывод действий должен жить во вкладке «Логи».

## Что изменено

### Discord probe после P02

Исторически кнопка `Проверить Discord` запускала весь `zap2_gui.app` через `sudo -A` ради чтения nft counters. P02 запрещает этот broad-root bridge: diagnostic probe не является основанием расширять root executor.

Текущее поведение:

- GUI privileged Discord probe помечен `staged/unsupported` и не запускает root Python из workspace;
- owner-run read-only diagnostics остаются доступны без расширения privilege surface;
- standard start/stop использует только `/usr/local/libexec/zap2-runtime-executor` с finite action ID и confirmed PlanHash;
- если для Discord counters в будущем понадобится root observation, она должна появиться отдельным bounded action с собственным contract/evidence, а не возвратом старой команды.

Историческая команда вида `sudo -A env PYTHONPATH=<workspace>/gui ... python -m zap2_gui.app ...` приведена только в истории проекта и **не должна использоваться как текущая инструкция**.

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
