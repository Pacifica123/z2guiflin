# Выборочный импорт v2rayNG

Здесь сохранены только upstream-файлы, которые служат прямой основой для VLESS profile parsing и Xray stream settings. Они изолированы от Python-кода и сохраняют GPL-3.0.

В `discord_tunnel.py` перенесены применимые идеи: расширенный набор VLESS query-полей, `httpupgrade`, `h2/http`, `kcp`, `grpc`, `xhttp`, TLS/REALITY-параметры и безопасная обработка `final mask`. Android UI, `VpnService`, MMKV, уведомления и мобильная маршрутизация не импортируются.
