# Заметки о Discord и TCP 5222

Статус: историческая запись эксперимента `v0.4-alpha Stage 7m`.

## Цель

В проект был перенесён узкий диагностический вариант из пользовательского Windows-пресета:

```text
community-discord-hostfakesplit-5222-minimal
```

Он отделён от смешанных YouTube/Discord стратегий и не выбирается автоматически.

## Почему проверялся порт 5222

Исходный Windows-пресет имел широкий WinDivert capture envelope:

```text
--wf-tcp-out=80,443,1080,2053,2083,2087,2096,5222,8443
```

Linux runtime не исполняет `--wf-*`. Поэтому порт был явно добавлен в Linux capture/filter область:

```text
--filter-tcp=80,443,1080,2053,2083,2087,2096,5222,8443
```

Это проверка гипотезы, а не утверждение, что TCP 5222 чинит updater Discord. Основные наблюдения того этапа всё ещё указывали на зависание соединений Cloudflare на TCP 443.

## Граница

- YouTube fallback отсутствует.
- Voice/STUN не включены.
- Стратегия остаётся owner-selectable.
- Windows WinDivert flags не копируются в Linux runtime.

## Ручная проверка

```bash
PYTHONPATH=gui python -m zap2_gui.app --select-strategy community-discord-hostfakesplit-5222-minimal
PYTHONPATH=gui python -m zap2_gui.app --default-start-plan
```

После запуска нужно сравнить endpoint report. Если Discord всё ещё остаётся на `Checking for updates`, а TCP 5222 не появляется, этот вариант не затрагивает текущий blocker.
