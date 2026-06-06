# GUI toggle и runtime logs

Основной GUI-поток включения и отключения Default теперь должен восприниматься как один toggle: `Включить Default` / `Выключить Default`. Пользователь не обязан вручную нажимать все промежуточные кнопки в обычном сценарии.

Если Default выключен, toggle делает цепочку:

1. проверяет build dependencies;
2. готовит build-plan;
3. подтверждает build-plan;
4. собирает `nfqws2` без sudo, если бинарник отсутствует;
5. готовит start-plan;
6. подтверждает start-plan;
7. вызывает `sudo -A` с графическим `SUDO_ASKPASS` helper для privileged start.

Если Default включён, toggle делает цепочку:

1. готовит stop-plan;
2. подтверждает stop-plan;
3. вызывает `sudo -A` с графическим `SUDO_ASKPASS` helper для privileged stop.

При неуспешном запуске toggle не должен оставаться в состоянии «включено». Status читается из runtime state, PID проверяется как принадлежащий текущему workspace, а owner-rules rollback должен быть виден в выводе и во вкладке `Логи`.

## Логи в GUI

Вкладка `Логи` показывает агрегированный read-only snapshot:

- последние runtime events из `.zap2/runtime/logs/default.runtime.jsonl`;
- tail `default.nfqws2.stdout.log`;
- tail `default.nfqws2.stderr.log`;
- размер и tail debug-log, если debug включён.

Эта вкладка ничего не исполняет, не меняет firewall и не запускает сервисы. Она нужна, чтобы причины падений вроде `nfq_create_queue(): Operation not permitted`, ошибок Lua или недоступных hostlist-файлов были видны прямо в GUI.

## Runtime inputs

GUI toggle использует public runtime copies для hostlist и Lua init-файлов под `/tmp/zap2-runtime-inputs/...`. Это нужно, потому что `nfqws2` намеренно сбрасывает привилегии и повторно проверяет доступность файлов после `dropcaps()`.
