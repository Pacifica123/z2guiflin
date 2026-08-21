# Patch summary

v0.4 stage8k: Discord machine/network diagnostics.

- Добавлен автономный `tools/discord_machine_diagnostics.py` без project/PyQt dependencies. Он можно копировать отдельно на Arch/Manjaro и запускать обычным пользователем.
- Probe агрегирует native pacman/pamac, Flatpak/Snap, desktop launchers, Discord/updater процессы, sanitized config/log evidence, route/DNS/time, active nfqws/Xray/VPN/Tor context и доступный read-only firewall context.
- Сеть разделена на updater manifest/download, app/API, Gateway WebSocket, CDN/media и secondary targets; обычный HTTPS используется как control для локализации Discord-specific path. IPv4/IPv6 TLS проверяются отдельно; HTTP/3 используется только при наличии соответствующей поддержки curl.
- Анализ классифицирует stale `updater_bootstrap`, updater/API/Gateway/CDN failures, `/etc/hosts`, proxy env, certificate/time errors, Wayland Flatpak permission hint и несколько параллельных установок.
- В «Диагностика» добавлена кнопка `Проверить Discord`. Standalone probe запускается асинхронно через `QProcess`.
- Результат открывается в themed flat dialog: человекочитаемое summary, рекомендации, сворачиваемый technical JSON и копирование. Цвета берутся из текущего theme profile.
- Privacy boundary: tokens/cookies/Local Storage не читаются; HOME и URL query strings редактируются в копируемом выводе; sudo и системные изменения отсутствуют.
- Добавлена русская документация `docs/DISCORD_MACHINE_DIAGNOSTICS.md` и regression suite `test_stage8k_discord_machine_diagnostics.py`.
