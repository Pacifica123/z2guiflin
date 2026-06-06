# Скелет GUI shell — v0.3-alpha_stage_5

## Решение этапа

Stage 5 вводит первый настоящий каркас desktop GUI. Это ещё не полнофункциональное приложение, но теперь у проекта есть стабильная форма PyQt shell: точка запуска, модель навигации, фабрика главного окна и placeholder-страницы для будущих разделов.

Главное правило этапа: **GUI можно импортировать и тестировать без установленного PyQt и без display server**. PyQt используется как локальная GUI-зависимость, но devctl-проверки не должны требовать оконной среды. Поэтому Qt-код изолирован за `qt_compat.py`, а pure Python модели и адаптеры остаются доступными в любой среде.

## Навигация

Начальная оболочка фиксирует шесть разделов:

- `Обзор` — сводка состояния проекта, ядра и ближайшего безопасного действия;
- `Ядро` — инвентаризация vendored-ядра, build units и будущий local build workflow;
- `Стратегии` — будущие профили, hostlists и параметры стратегий;
- `Диагностика` — будущие read-only проверки, discovery и отчёты;
- `Настройки` — язык, пути, политика подтверждений и developer-oriented параметры;
- `Логи` — будущая история операций, dry-run планов, проверок и результатов исполнения.

Раздел `Ядро` уже опирается на `CORE_INVENTORY.json` и `BUILD_MAP.json`. Остальные разделы намеренно являются placeholder-страницами, чтобы следующими патчами развивать их независимо и не смешивать навигационный каркас с business logic.

## Файлы GUI-слоя

```text
gui/zap2_gui/
  app.py                    CLI-visible entry point и optional GUI launcher
  qt_compat.py              безопасная проверка доступности PyQt6
  qt_app.py                 QApplication bootstrap
  adapters/gui_state.py     read-only state assembly для оболочки
  adapters/local_build.py   plan-only adapter локальной сборки ядра
  models/navigation.py      pure Python модель разделов
  windows/main_window.py    фабрика главного окна PyQt
  widgets/placeholders.py   начальные placeholder widgets
```

Qt-классы не должны импортироваться на верхнем уровне модулей, которые нужны тестам. Если PyQt6 не установлен, `python -m zap2_gui.app` должен по-прежнему показывать текстовое описание проекта, а `python -m zap2_gui.app --gui` должен завершаться понятным сообщением о недостающей локальной зависимости.

## Зависимость PyQt

Stage 5 добавляет PyQt6 как optional dependency `gui`, а не как обязательное требование для всех проверок. Это важно: разработчик может поставить GUI-зависимость локально, но автоматические structural checks остаются лёгкими и не требуют системного Qt/display окружения.

Пример локального запуска после установки GUI-зависимости:

```bash
python -m zap2_gui.app --gui
```

Команда предназначена для машины владельца/разработчика. Автоматические devctl-проверки не запускают GUI и не пытаются эмулировать desktop session.

## Не-цели Stage 5

Этот этап не реализует сборку ядра, запуск `make`, управление сервисами, firewall, systemd, runtime lifecycle или privileged actions. Он только создаёт форму будущего приложения, чтобы следующие изменения развивались внутри стабильной навигационной модели.

## Связь с local build adapter

Начиная со Stage 6, раздел `Ядро` получает не только inventory/build map, но и default local build plan. Это пока не кнопка запуска сборки: GUI показывает смысл команды, target и ожидаемые артефакты. Исполнение `make` должно появиться отдельным runner-слоем после явных подтверждений владельца.

## Stage 7: вкладка `Стратегии` получает данные

До Stage 7 раздел `Стратегии` был placeholder. Теперь он становится `profiles-backed`: GUI может читать `profiles/default.json`, `strategies/catalog.json` и файлы стратегий через pure Python adapter `workspace_profiles.py`.

Это всё ещё не редактор и не runtime executor. Страница должна показывать владельцу:

- доступные workspace-профили;
- стратегию, связанную с выбранным профилем;
- build target, который профиль считает основным;
- локальные hostlists;
- safety boundary: read-only, без `sudo`, без service/firewall mutation.

Такой порядок важен для архитектуры GUI: сначала видимость данных, затем редактирование, затем dry-run plans, затем подтверждённое владельцем применение.

## v0.3-beta Stage 4: Default strategy import и GUI runtime controls

Stage 4 переносит первую базовую стратегию из Windows GUI: `Default v1 (game filter)`. Перенос частичный и контролируемый: оригинальный Windows preset хранится как reference, а Linux runtime получает только seed hostlist и минимальные `nfqws2`-совместимые Lua-аргументы. Полный WinDivert preset не исполняется напрямую.

Также Stage 4 переносит CLI build/start/stop/status workflow во вкладку `Обзор` PyQt shell. GUI не запускает `sudo` и не применяет firewall скрыто: он готовит планы, подтверждает plan id через существующий confirmation gate и показывает owner-команды для терминала.
