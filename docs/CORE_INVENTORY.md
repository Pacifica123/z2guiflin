# Инвентаризация ядра — v0.3-alpha_stage_4

Этот документ фиксирует первый read-only снимок vendored-ядра `core/zapret2/`. Он нужен не для запуска ядра, а для того, чтобы GUI и будущие адаптеры понимали фактическое устройство исходного дерева: где находятся Makefile, C-исходники, Lua-сценарии, конфигурационные заготовки, service templates и зоны, требующие ручного контроля владельца.

Машиночитаемая версия снимка находится в `core/zapret2/CORE_INVENTORY.json`. Она генерируется и проверяется скриптом `tools/gui_checks/inventory_core.py`, который только читает файлы и не запускает upstream-сценарии.

## Граница Stage 4

Stage 4 делает только инвентаризацию:

- не собирает C-код;
- не запускает `make`;
- не запускает `install_easy.sh`, `install_bin.sh`, `install_prereq.sh`, `uninstall_easy.sh` или `blockcheck2.sh`;
- не использует `sudo`;
- не меняет firewall, systemd, nftables/iptables, ipset или сетевое состояние;
- не обращается в сеть.

Это важно: мы начинаем стабильную разработку от фактической карты ядра, а не от автоматизированной установки.

## Сводка дерева

По снимку Stage 4 в vendored-ядре зафиксировано **245 файлов** upstream-импорта. Это число намеренно совпадает с `importedFileCount` из `core/zapret2/UPSTREAM_IMPORT.json` и не включает наши служебные файлы `CORE_INVENTORY.json`, `BUILD_MAP.json`, `UPSTREAM_IMPORT.json`, `UPSTREAM_IMPORT.md`.

Крупнейшие области дерева:

| Область | Количество файлов | Роль |
| --- | ---: | --- |
| `nfq2/` | 68 | основной C-компонент `nfqws2` и связанные платформенные файлы |
| `files/` | 46 | upstream binary/profile payload-файлы из исходного дерева |
| `init.d/` | 36 | шаблоны интеграции с init/service-системами |
| `blockcheck2.d/` | 20 | сценарии и данные для blockcheck-style discovery |
| `ipset/` | 20 | сценарии и заготовки списков |
| `docs/` | 20 | upstream-документация и compile notes |
| `common/` | 13 | общие shell-библиотеки upstream-сценариев |
| `lua/` | 6 | Lua-логика стратегий/профилей |
| `ip2net/` | 4 | helper для обработки IP/net данных |
| `mdig/` | 2 | DNS-helper |

## Типы файлов

Снимок показывает, что ядро сейчас состоит не только из C-кода. В нём есть shell-обвязка, Lua-слой, init-шаблоны, конфиги, списки и upstream-документация.

Ключевые типы:

| Тип | Количество | Комментарий |
| --- | ---: | --- |
| `.sh` | 55 | shell-сценарии upstream; не запускать из автоматических проверок |
| `.bin` | 46 | upstream payload/data-файлы, сохранённые как source input |
| `.h` | 35 | C-заголовки |
| `.c` | 32 | C-исходники |
| `<none>` | 34 | исполняемые/текстовые файлы без расширения, в том числе init/custom examples |
| `.txt` | 22 | списки, readme и примеры |
| `.lua` | 6 | Lua-стратегии и библиотечные сценарии |
| `.service` / `.timer` | 4 | systemd-шаблоны и таймер |

## Makefile и исходники

Первичные Makefile, которые будущий build adapter должен знать первыми:

- `core/zapret2/Makefile` — корневой делегатор сборки;
- `core/zapret2/nfq2/Makefile` — сборка `nfqws2`;
- `core/zapret2/ip2net/Makefile` — сборка `ip2net`;
- `core/zapret2/mdig/Makefile` — сборка `mdig`.

Дополнительные Makefile есть в `docs/compile/openwrt/package/zapret/...` и `nfq2/BSDmakefile`; они считаются reference/build-packaging input, а не первичным Linux GUI build path на этом этапе.

Основные source-директории:

- `nfq2/` и `nfq2/crypto/` — большая часть C-исходников основного компонента;
- `nfq2/andr/` — Android-specific исходники;
- `ip2net/` — helper-исходники;
- `mdig/` — DNS-helper;
- `lua/` — Lua-слой стратегий.

## Конфигурационные и runtime-зоны

Особого внимания требуют:

- `config.default` — upstream default config seed;
- `ipset/zapret-hosts-user-exclude.txt.default` — заготовка пользовательских исключений;
- `init.d/systemd/*.service` и `*.timer` — шаблоны service integration;
- `common/linux_fw.sh`, `common/nft.sh`, `common/ipt.sh` — зоны firewall-related логики;
- `common/linux_daemons.sh` и `common/elevate.sh` — зоны daemon/elevation логики;
- `install_*.sh`, `uninstall_easy.sh`, `blockcheck2.sh` — root-level upstream workflows.

Эти файлы полезны как source input и справочник поведения, но они не становятся автоматическими действиями GUI. Будущий GUI должен сначала показывать план, затем просить явное решение владельца, и только потом владелец может выполнять локальное действие на своей машине.

## Как обновлять снимок

Для разработчика допустима ручная перегенерация snapshot-файлов после осознанного изменения ядра:

```bash
python tools/gui_checks/inventory_core.py --write
python tools/gui_checks/inventory_core.py --check
```

Автоматические проверки патча используют только `--check`. Они не компилируют и не запускают upstream-код.
