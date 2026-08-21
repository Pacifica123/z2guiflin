# Project tools

`tools/` теперь разделён на несколько зон, чтобы обычные проверки не смешивались
с meta-инструментами и будущими низкоуровневыми экспериментами.

- `gui_checks/` — read-only проверки проекта, GUI/runtime workflow и снимка
  vendored `core/zapret2/`. Эти скрипты не используют сеть, не требуют sudo и не
  меняют firewall/service state.
- `experimental/` — место для будущих прототипов, которые ещё не являются частью
  стабильного GUI/runtime workflow.
- `lowlevel/` — место для будущих низкоуровневых утилит уровня TCP parser,
  Ethernet-less IPv4 header parser и похожих инструментов рядом с nfqws2.

Инструменты, обслуживающие сам процесс патчей и рабочие области, лежат отдельно
в `meta_tools/`.
- `discord_machine_diagnostics.py` — автономная read-only диагностика Discord на текущей Arch-like машине: установки, updater/process/log context, DNS/TLS/HTTPS/Gateway/CDN и текущие сетевые обходы. Скрипт не зависит от проекта и может запускаться отдельно; подробности — `docs/DISCORD_MACHINE_DIAGNOSTICS.md`.

