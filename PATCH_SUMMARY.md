# Локальный SOCKS5 туннеля: пароль и случайный порт

База — патч `2026-10-15-reproducible-tests` той же пачки, product 1.1.0 (версия не меняется).

Локальный SOCKS туннеля Xray/V2Ray больше не открывается без аутентификации. Inbound использует RFC1929 со случайными учётными данными на каждую сессию: они хранятся в `.zap2/tunnel/runtime/*-socks-auth.json` с правами 0600, в plan/status/report/логах показаны как `<redacted>`, а в plan попадает только fingerprint. Порт по умолчанию — случайный свободный в 20000–60999 вне сканируемых (10808, 1080, 9000, 16000–16100); явно заданный порт сохраняется. Probe проверяет пароль и помечает listener, принимающий NO_AUTH, как `T0_SOCKS_INSECURE_NOAUTH`. Угроза — wiki.zapret.moe/VLESS-SOCKS5-vulnerability (07.04.2026); инвариант проекта «localhost ≠ private».

Chromium `--proxy-server` не поддерживает SOCKS-аутентификацию. Поэтому запуск Discord/Vesktop режимами socks-updater-window, socks-full-session и socks-flag-only возможен только с явным `--tunnel-socks-legacy-noauth`, с предупреждением в plan/launch-текстах. Без флага работает socks-env-only (креды в `ALL_PROXY`/`HTTPS_PROXY`). Сессии, записанные до патча, считаются legacy no-auth.

Contract: `gui/zap2_gui/app.py` получил опцию `--tunnel-socks-legacy-noauth`, а у `--tunnel-socks-port` default 0 (auto). Хеш app.py осознанно перепривязан в `runtime/v11/pre-forensics.json` (preservedAuthorities) и `runtime/p06/pre-forensics.json` (authorities), `docs/generated/reference.json` регенерирован. Документация: `docs/operations/troubleshooting.md`. Доска: карточка перенесена в «Сделано», добавлены «Приёмка на хосте» и ADR по Chromium. v1.1 source freeze пересчитан.
