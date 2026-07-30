# План SOCKS5/VLESS tunnel lane для Discord

Статус: реализованный экспериментальный контур Stage 7p–8c. Текущая краткая граница описана в `PROJECT_STATUS.md`.

## Проблема

Zapret-стратегия может не подходить конкретному DPI или маршруту. Для такого случая нужен независимый путь через локальный SOCKS5 и внешний VLESS-compatible core.

Проект не реализует VLESS самостоятельно. Он управляет внешним `xray`, `v2ray` или `sing-box` как отдельным процессом.

## Архитектура

```text
VLESS share URI
-> локальный redacted connection profile
-> generated core config
-> external core
-> loopback SOCKS5
-> probe
-> запуск Discord с proxy settings
```

Tunnel lane отделён от `nftables`/NFQUEUE runtime. Он не требует `sudo`, пока не используется будущий TUN/TProxy режим.

## Модель профиля

Из `vless://` извлекаются:

```text
uuid
server
port
transport type
security/tls/reality fields
sni/serverName
path/host/serviceName
remarks
```

Секретные значения не печатаются в обычный output. Состояние хранится в `.zap2/tunnel/`, по возможности с mode `0600`.

## Импорт

```bash
PYTHONPATH=gui python -m zap2_gui.app \
  --tunnel-connection-import-vless 'vless://...'

PYTHONPATH=gui python -m zap2_gui.app --tunnel-connections
PYTHONPATH=gui python -m zap2_gui.app \
  --tunnel-select-connection <connection-id>
```

GUI также поддерживает clipboard import и batch extraction без показа полного URI.

## Внешний core

```bash
PYTHONPATH=gui python -m zap2_gui.app \
  --discord-tunnel-plan \
  --tunnel-core-binary /path/to/xray \
  --tunnel-core-kind xray
```

Поддерживаемые kinds:

```text
auto
xray
v2ray
sing-box
```

Plan генерирует redacted preview, core config path, SOCKS port и managed runtime state. Наличие binary проверяется до start.

## Жизненный цикл

```bash
PYTHONPATH=gui python -m zap2_gui.app --discord-tunnel-start
PYTHONPATH=gui python -m zap2_gui.app --discord-tunnel-status
PYTHONPATH=gui python -m zap2_gui.app --discord-tunnel-stop
```

Остановка касается только PID, записанного tunnel runtime. Случайный внешний процесс не завершается.

## Проверки

### Проверка core/SOCKS

```bash
PYTHONPATH=gui python -m zap2_gui.app --discord-tunnel-probe
```

Проверяется managed PID и доступность loopback SOCKS port.

### HTTPS через SOCKS

```bash
PYTHONPATH=gui python -m zap2_gui.app --discord-tunnel-https-probe
```

По умолчанию используется harmless HEAD/HTTPS check к `updates.discord.com`. Host/path/timeout можно переопределить.

### Диагностика маршрута

```bash
PYTHONPATH=gui python -m zap2_gui.app --discord-tunnel-route-diagnose
```

Команда сводит core state, SOCKS probe, HTTPS preflight и логи в короткий verdict.

## Запуск Discord

```bash
PYTHONPATH=gui python -m zap2_gui.app \
  --discord-launch-through-socks \
  --discord-launch-preflight
```

Preflight блокирует запуск Electron в заведомо сломанный route. Для ручного эксперимента существует явный override:

```text
--discord-launch-allow-failed-preflight
```

Запущенная process group может быть остановлена через:

```bash
PYTHONPATH=gui python -m zap2_gui.app --discord-stop-launched
```

## Пошаговый запуск

```bash
PYTHONPATH=gui python -m zap2_gui.app --discord-tunnel-guided-run
```

Цикл включает plan, confirmation, start, probe, launch и owner verdict. Он сохраняет отчёт, но не считает network success автоматически по одному открытому socket.

## Взаимодействие с Zapret

По умолчанию параллельный запуск tunnel и default Zapret ограничен, чтобы избежать неоднозначного route. Для явного launch composer эксперимента используется:

```text
--tunnel-allow-zapret-parallel
```

Порядок запуска и остановки задаёт launch composer.

## TUN/TProxy

```bash
PYTHONPATH=gui python -m zap2_gui.app --discord-tunnel-tun-plan
```

Это только research plan. Реальная прозрачная маршрутизация, policy routing и привилегированные правила в v0.4 не реализованы.

## Критерии полезности tunnel lane

Минимальный полезный уровень:

- профиль импортирован без утечки секрета;
- внешний core запускается и останавливается как managed process;
- SOCKS port доступен;
- HTTPS preflight через SOCKS проходит;
- Discord действительно запущен с ожидаемыми proxy settings;
- failure verdict различает core, local SOCKS, upstream TLS и launch lifecycle.

Успех одного probe не гарантирует работу Discord updater/voice.

## Открытые недостатки

- нет subscription manager;
- нет автоматического выбора upstream;
- нет keyring;
- нет per-app policy routing;
- нет TUN/TProxy;
- нет WireGuard/OpenVPN;
- нет автоматического fallback между Zapret и tunnel.

Полный список: `KNOWN_GAPS_CHECKLISTS.md`.
