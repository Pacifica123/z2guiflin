# Диагностика Discord на текущей машине

`tools/discord_machine_diagnostics.py` — автономная read-only утилита для Arch-like Linux. Она не зависит от `zap2_gui`, PyQt или сторонних Python-пакетов и может быть скопирована отдельно на другую машину с Python 3.10+.

## Что проверяется

Локальный контекст:

- native-установки из общей базы `pacman/pamac`, включая stable/PTB/Canary и известные Electron-варианты;
- Flatpak и, если установлен, Snap;
- `desktop` launchers и найденные Discord/Vesktop binaries;
- текущие Discord и `updater_bootstrap` процессы, их возраст и доступные socket-состояния;
- активные `nfqws/nfqws2`, Xray/V2Ray, sing-box, OpenVPN, WireGuard, Tor и похожие сетевые процессы;
- `ip route`, `ip rule`, `resolvectl`, `timedatectl`; `nft list ruleset` выполняется только как обычный read-only вызов и не повышает привилегии;
- `/etc/hosts` overrides для Discord;
- только разрешённые диагностические ключи `settings.json`, без token/local storage;
- небольшие фрагменты локальных Discord logs и user journal, отфильтрованные по updater/network/TLS/Gateway ошибкам;
- история Discord-пакетов из `/var/log/pacman.log`.

Сетевой контекст:

- системный DNS для updater, API, Gateway, CDN/media и secondary hosts;
- TLS отдельно по одному IPv4 и IPv6 адресу, если они доступны;
- Linux updater manifest `updates.discord.com/distributions/app/manifests/latest`;
- `discord.com/api/v10/gateway`;
- настоящий WebSocket Upgrade к `gateway.discord.gg`;
- CDN HTTP/TLS;
- HTTP/3 через `curl --http3-only`, только если локальная сборка curl заявляет HTTP/3;
- контрольный обычный HTTPS endpoint. Он нужен, чтобы отличать общую поломку сети от Discord-specific path.

## Запуск отдельно

```bash
python tools/discord_machine_diagnostics.py
python tools/discord_machine_diagnostics.py --json
python tools/discord_machine_diagnostics.py --no-network
```

Для переноса на другую Arch/Manjaro-машину достаточно скопировать один файл `discord_machine_diagnostics.py` и выполнить его обычным пользователем.

## GUI

Во вкладке «Диагностика» блок «Discord: состояние машины и сети» запускает тот же файл через `QProcess`, поэтому интерфейс не зависает на сетевых timeout.

После завершения открывается themed dialog:

- сверху — человекочитаемый итог и ограниченный список следующих действий;
- «Техническая информация» — сворачиваемый sanitized JSON из standalone probe;
- кнопка копирования копирует именно технический блок.

Dialog не задаёт собственную фиксированную палитру: фон, border, accent и semantic status colors берутся из текущего theme profile.

## Ограничения и приватность

Probe не запускает Discord специально. Он анализирует уже существующие процессы/логи и выполняет собственные bounded network probes. Это сделано намеренно: автоматический запуск двух разных экземпляров Discord сам менял бы наблюдаемое состояние и мог бы затронуть пользовательскую сессию.

Probe не читает Discord tokens, Local Storage и cookies. Домашний каталог заменяется на `~`, query string URL редактируется в выводе, proxy credentials не выводятся. Локальные/private IP могут оставаться в техническом блоке, потому что они нужны для диагностики route/DNS. Перед публикацией отчёта вне доверенного контекста его всё равно нужно просмотреть.

Успешный probe под активным Zapret/VPN/Xray описывает именно этот текущий маршрут. Для сравнения с провайдерским direct path нужно повторить probe в явно известном другом состоянии.
