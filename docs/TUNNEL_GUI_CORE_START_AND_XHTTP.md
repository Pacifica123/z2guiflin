# Tunnel GUI core start and xhttp compatibility

Дата: 2026-06-29

## Найденный UX-баг

Пользователь нажимал «Запустить Discord через SOCKS», но tunnel core уже был в состоянии `failed`.

По `.zap2` причина была в stderr core:

```text
unknown transport protocol: xhttp
```

Импортированный VLESS profile использовал `type=xhttp`, а выбранный `/usr/bin/v2ray` отверг этот transport.

## Что изменено

### Tunnel tab

Добавлен явный блок `Tunnel core`:

- поле `Core binary`;
- кнопка `План core`;
- кнопка `Запустить tunnel core`;
- кнопка `Остановить tunnel core`;
- кнопка `SOCKS probe`.

Теперь GUI показывает порядок действий:

```text
импорт profile -> запустить tunnel core -> SOCKS probe -> запустить Discord через SOCKS
```

Кнопка `Запустить Discord через SOCKS` больше не выглядит как кнопка, которая сама поднимет core.

### Adapter diagnostics

Если session state=`failed`, status/probe/launch выводят tail `default.core.stderr.log`.

Если stderr содержит `unknown transport protocol`, выводится диагноз:

```text
core rejected the generated config transport
```

Для `type=xhttp/splithttp` + `v2ray` plan/start показывают compatibility warning. Start не запускает core заведомо несовместимым сочетанием.

## Что делать пользователю

Для VLESS `type=xhttp` нужно выбрать совместимый core или импортировать другой profile.

GUI больше не должен советовать просто “start then probe”, когда предыдущий start уже умер на несовместимом transport.
