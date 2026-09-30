# C Tor, Arti и выборочный импорт v2rayNG

## Решение

- C Tor остаётся системным пакетом Arch Linux и запускается как managed process через `/usr/bin/tor`.
- Arti оформлен отдельным backend и запускается через `arti proxy -c <config>`.
- Оба backend публикуют только loopback SOCKS и не меняют nftables, systemd или firewall.
- Bridges и pluggable transports не входят в этот патч.
- Из v2rayNG напрямую сохранены только файлы VLESS format/profile/transport builder и GPL-3.0 license.
- Python-адаптация расширяет существующий VLESS parser, но не переносит Android UI и `VpnService`.

## Runtime

```text
.zap2/tor/generated/
.zap2/tor/data/
.zap2/tor/runtime/
.zap2/tor/logs/
```

После запуска Tor backend обновляет общий `.zap2/tunnel/runtime/<profile>.session.json`. Поэтому существующие SOCKS probe и запуск Discord используют Tor без отдельного дублирования route layer.

## CLI

```bash
PYTHONPATH=gui python -m zap2_gui.app --tor-backend arti --tor-backend-plan
PYTHONPATH=gui python -m zap2_gui.app --runtime-confirm runtime-default-tor-arti-start-plan
PYTHONPATH=gui python -m zap2_gui.app --tor-backend arti --tor-backend-start --confirm runtime-default-tor-arti-start-plan
PYTHONPATH=gui python -m zap2_gui.app --tor-backend-status
PYTHONPATH=gui python -m zap2_gui.app --discord-tunnel-probe
PYTHONPATH=gui python -m zap2_gui.app --tor-backend-stop
```

Для C Tor заменить `arti` на `c-tor`.
