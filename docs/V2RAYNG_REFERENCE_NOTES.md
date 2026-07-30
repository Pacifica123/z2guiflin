# Reference-заметки по v2rayNG для tunnel lane

Статус: справка по происхождению идей Stage 7p/7y.

## Граница лицензии и переноса

v2rayNG является Android/Kotlin проектом под GPL-3.0. В z2guiflin не копируется его implementation code. Используются только общие продуктовые идеи, реализованные заново на Python/Linux.

## Полезные идеи

- Сначала разобрать share URI в локальную модель профиля, затем генерировать core config.
- Явно задавать loopback SOCKS inbound и порт, например `10808`.
- Разделять proxy-only и VPN/TUN режимы.
- Делать sniffing для `http`, `tls`, `quic` видимым в generated JSON.
- Хранить процесс внешнего core как managed lifecycle с явной остановкой.
- Рассматривать per-app routing как отдельную Linux-задачу.

## Что не переносится

- Android `VpnService`;
- activities/fragments и MMKV;
- выбор Android package UID;
- mobile lifecycle assumptions;
- чужие configs, credentials и Kotlin code.

## Адаптация

```text
v2rayNG share profile   -> tunnel connection profile z2guiflin
local SOCKS             -> loopback SOCKS inbound
proxy-only              -> external-core proxy runtime
VPN mode                -> отдельная будущая TUN/TProxy ветка
per-app proxy           -> Linux launcher/policy routing
```

## Импорт из буфера обмена

В Stage 7y перенесён только UX-pattern:

```text
clipboard text
-> извлечь vless://
-> при необходимости декодировать base64 subscription
-> импортировать несколько links
-> показать redacted summary
-> обновить список профилей
```

Импорт не запускает core, не вызывает `sudo`, не меняет firewall и не запускает Discord.

## Секреты

В репозитории допустим только redacted пример:

```text
vless://<uuid>@<server>:<port>?type=tcp&encryption=none#<remarks>
```

Полные URI и UUID хранятся только в `.zap2/tunnel` с ограниченными правами доступа.
