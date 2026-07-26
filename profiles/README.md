# Контексты запуска workspace

`profiles/` — историческое имя каталога. Файлы здесь не являются profile-блоками
Zapret2. Они описывают локальный контекст запуска: build target, owner-maintained
hostlists, safety boundary и выбранный preset id в совместимом поле
`strategyId`.

Точный смысл структуры:

```text
workspace runtime context -> выбранный preset -> ordered traffic profiles
```

Настоящие исполнимые пресеты лежат в `presets/`, а один traffic-профиль является
блоком между `--new` внутри `.txt`.

Контекст запуска сам по себе:

- не запускает `make`;
- не вызывает `sudo`;
- не управляет `systemd`, `nftables` или firewall;
- не меняет hostlists автоматически;
- только даёт данные существующему plan/confirmation/runtime workflow.

Старые имена `WorkspaceProfile`, `--list-profiles` и `profileId` сохраняются до
отдельной миграции runtime state.

## Default hostlist

`profiles/hostlists/default.hosts` остаётся owner-maintained seed для YouTube и
Discord desktop non-voice. Наличие домена в hostlist не гарантирует, что один и
тот же traffic-профиль подходит каждому сервису. Для этого пресет должен иметь
отдельные профильные фильтры и стратегии в правильном порядке.
