# Build map ядра — v0.3-alpha_stage_4

Build map — это карта будущей локальной сборки vendored-ядра `core/zapret2/`. Она не является установщиком и не является runtime-инструкцией. Её задача — превратить фактические Makefile в понятные данные, которые позже сможет показать GUI: какие компоненты существуют, какие targets объявлены, какие outputs ожидаются и где проходят границы автоматических проверок.

Машиночитаемая версия находится в `core/zapret2/BUILD_MAP.json` и проверяется `tools/gui_checks/inventory_core.py --check`.

## Политика Stage 4

Автоматические проверки Stage 4 могут:

- читать Makefile;
- парсить targets;
- сверять snapshot-файлы с текущим деревом;
- проверять наличие исходников и документации.

Автоматические проверки Stage 4 не могут:

- запускать `make`;
- устанавливать build dependencies;
- использовать `sudo`;
- запускать upstream install/uninstall/blockcheck scripts;
- менять systemd, firewall, ipset, nftables или iptables.

Так мы сохраняем скорость разработки без возвращения к проблеме “установщик раньше архитектуры”.

## Корневой Makefile

`core/zapret2/Makefile` является делегатором. Он объявляет основные цели:

| Target | Смысл для build map |
| --- | --- |
| `all` | обычная делегированная сборка под Linux-подобную среду |
| `systemd` | вариант сборки с systemd-related compile flag в дочернем `nfq2` |
| `android` | делегированный Android-вариант |
| `bsd` | делегированный BSD-вариант |
| `clean` | очистка outputs и делегирование clean в дочерние каталоги |

Корневой Makefile делегирует сборку в:

- `nfq2/`;
- `ip2net/`;
- `mdig/`.

Ожидаемая директория агрегированных outputs по upstream Makefile: `binaries/my`.

## Компоненты сборки

### `nfqws2`

`nfqws2` — основной build unit в текущем дереве `zapret2`.

- Makefile: `nfq2/Makefile`;
- основные source roots: `nfq2/`, `nfq2/crypto/`, `nfq2/andr/`;
- Linux output по Makefile: `nfq2/nfqws2`;
- дополнительные outputs для других платформ: `nfq2/dvtws2`, `nfq2/winws2.exe`;
- заявленные Linux-библиотеки: zlib, libnetfilter_queue, libnfnetlink, libmnl, libm, LuaJIT или Lua.

Known targets: `all`, `nfqws2`, `ubsan`, `systemd`, `android`, `bsd`, `cygwin64`, `cygwin32`, `cygwin`, `clean`.

### `ip2net`

`ip2net` — helper build unit для обработки IP/net данных.

- Makefile: `ip2net/Makefile`;
- source files: `ip2net/ip2net.c`, `ip2net/qsort.c`;
- Linux output: `ip2net/ip2net`;
- дополнительные macOS-related intermediate outputs по Makefile: `ip2net/ip2neta`, `ip2net/ip2netx`.

Known targets: `all`, `ip2net`, `systemd`, `android`, `bsd`, `mac`, `win`, `clean`.

### `mdig`

`mdig` — DNS-helper build unit.

- Makefile: `mdig/Makefile`;
- source files: `mdig/*.c`;
- Linux output: `mdig/mdig`;
- заявленная Linux-библиотека: pthread;
- дополнительные macOS-related intermediate outputs по Makefile: `mdig/mdiga`, `mdig/mdigx`.

Known targets: `all`, `mdig`, `systemd`, `android`, `bsd`, `mac`, `win`, `clean`.

## Контракт будущего build adapter

Следующий слой разработки должен соблюдать такой порядок:

1. представить build plan как данные;
2. показать владельцу, какие Makefile, targets, outputs и host dependencies будут затронуты;
3. дать владельцу запустить локальную сборку явно;
4. сохранить результат сборки и логи как артефакт разработки;
5. не смешивать сборку с установкой, service management или firewall mutation.

GUI может позже иметь кнопку “собрать ядро”, но эта кнопка должна строиться на build map и явном плане. Она не должна превращаться в скрытый installer.

## Использование в Stage 6

Stage 6 использует `BUILD_MAP.json` как источник правды для local build adapter. Adapter не парсит Makefile заново и не запускает `make`: он читает уже проверенную карту, строит план команды и отдаёт его GUI/CLI как данные.

Это важно для устойчивости: если build map изменится, тесты adapter-слоя покажут расхождение в поддерживаемых целях, командах или ожидаемых артефактах.
