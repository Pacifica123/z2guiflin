# Patch summary

Stage 8g добавляет системный C Tor backend, отдельный Arti backend и выборочный прямой импорт применимой VLESS-логики v2rayNG.

- C Tor и Arti запускаются как отдельные managed процессы без sudo/firewall/systemd.
- Общая SOCKS route session позволяет использовать существующие probes и Discord launcher.
- Arti archive подтверждён как официальный Tor Project source и зафиксирован по commit/SHA-256.
- Сохранены selected upstream-файлы v2rayNG и GPL-3.0; Android-only слой исключён.
- VLESS parser/config расширен для xhttp/httpupgrade/h2/kcp/grpc и дополнительных TLS/REALITY полей.
- Guided tunnel tests выделяют свободные loopback-порты динамически и не конфликтуют с локальными сервисами владельца.
