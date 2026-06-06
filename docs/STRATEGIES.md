# Стратегии

Stage 7 вводит каталог **стратегий**. Стратегия — это не shell script и не набор низкоуровневых команд. Это описание типа workflow, который GUI должен показать владельцу.

## Где лежат стратегии

```text
strategies/
  README.md
  catalog.json
  manual-local.json
  read-only-diagnostics.json
```

`strategies/catalog.json` перечисляет файлы стратегий и фиксирует общий safety contract: автоматические проверки не исполняют стратегии, а сами стратегии на Stage 7 являются plan-only описаниями.

## Текущие стратегии

`manual-local` — основная стратегия по умолчанию. Она следует философии `toolbox/apothecary`: GUI должен быть набором понятных инструментов, рецептов и планов, а не чёрным ящиком, который тайно применяет системные изменения.

`read-only-diagnostics` — безопасная стратегия-заглушка для будущего диагностического workflow. Она показывает, что каталог может содержать разные сценарии без немедленного исполнения.

## Что стратегия может описывать

Стратегия описывает:

- философию workflow;
- для чего она предназначена;
- последовательность высокоуровневых шагов вроде `inspect -> plan -> present`;
- capabilities, которые GUI может отобразить;
- ограничения Stage 7.

Стратегия не содержит команд `sudo`, не меняет службы, не управляет firewall и не запускается автоматически.

## CLI

```bash
PYTHONPATH=gui python -m zap2_gui.app --list-strategies
PYTHONPATH=gui python -m zap2_gui.app --show-strategy manual-local
```

Так мы получаем основу для будущей вкладки `Стратегии`: сначала видимые данные и валидация, затем редактор профиля, и только позднее — owner-confirmed runtime lifecycle.

## v0.3-beta Stage 4: Default strategy import и GUI runtime controls

Stage 4 переносит первую базовую стратегию из Windows GUI: `Default v1 (game filter)`. Перенос частичный и контролируемый: оригинальный Windows preset хранится как reference, а Linux runtime получает только seed hostlist и минимальные `nfqws2`-совместимые Lua-аргументы. Полный WinDivert preset не исполняется напрямую.

Также Stage 4 переносит CLI build/start/stop/status workflow во вкладку `Обзор` PyQt shell. GUI не запускает `sudo` и не применяет firewall скрыто: он готовит планы, подтверждает plan id через существующий confirmation gate и показывает owner-команды для терминала.
