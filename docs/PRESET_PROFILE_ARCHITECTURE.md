# Архитектура «пресет → профили»

## Кратко

Новая предметная модель z2guiflin повторяет реальную модель Zapret2:

```text
пресет
  -> глобальные параметры nfqws2
  -> упорядоченные traffic-профили
       -> filter
       -> strategy / lua-desync
       -> range
       -> direction
```

Пресет является целым `.txt`-файлом. Профиль является одним блоком внутри него.
Следующий профиль начинается после `--new`. Порядок блоков важен: nfqws2
проверяет их сверху вниз и выбирает первое совпадение.

## Разведение старых терминов

Раньше проект использовал слово `profile` для файла `profiles/default.json`.
Этот объект не является профилем Zapret2. Он хранит build target, hostlist и
выбор текущей стратегии. Теперь его точное имя — **workspace runtime context**,
или по-русски **контекст запуска**.

Старое имя `WorkspaceProfile`, CLI `--list-profiles` и поле `strategyId`
сохранены как совместимые алиасы. Они не должны использоваться при разработке
нового редактора пресетов.

Слово **профиль** без уточнения теперь означает только traffic-профиль Zapret2:
один блок фильтра и действий внутри пресета.

## Где хранятся данные

```text
profiles/default.json
    legacy workspace runtime context

strategies/*.json
    метаданные пресета: title, source, service target, safety, notes

presets/workspace/*.txt
    канонические исполнимые параметры nfqws2

presets/generated/*.txt
    пресеты, созданные Blockcheck exporter
```

Каждый JSON metadata-файл получает `presetPath`. Поле `runtimeArgs` пока
сохраняется как контрольная копия. Загрузчик читает `.txt`, собирает argv и
требует полного совпадения с `runtimeArgs`. Это позволяет перейти на новую
структуру без незаметного изменения работающих аргументов.

## Внутренняя модель

`models/preset.py` содержит четыре основные сущности:

- `ZapretPreset` — глобальные параметры и ordered profiles;
- `TrafficProfile` — один профиль и его исходные аргументы;
- `TrafficFilter` — tcp/udp/l3/l7, hostlist и ipset-условия;
- `PresetAction` — один `--lua-desync` с эффективными payload/range/direction.

Range и payload действуют на все последующие `--lua-desync` до
переопределения. Поэтому они записываются не только как общий текст профиля, но
и как эффективные значения каждого действия. Это исключает ошибочное
представление сложного профиля как одной пары range.

## Round-trip

Главное условие первого этапа миграции:

```text
parse(preset args).to_runtime_args() == исходные preset args
```

Парсер не переставляет опции, не нормализует значения и не добавляет `--new`.
Следовательно, текущий runtime получает тот же argv, что и до патча.

## GUI

Вкладка `Стратегии` заменена вкладкой `Пресеты`.

Левая часть показывает каталог пресетов. Правая часть показывает таблицу
профилей выбранного пресета:

```text
# | Профиль | Фильтр | Стратегия | Range | Direction
```

Ни чтение каталога, ни выбор строки не запускают nfqws2. Кнопка выбора пресета
использует прежний `.zap2` selection и прежнюю границу plan/confirmation.

## Совместимость

На этом этапе сохраняются:

- `strategies/catalog.json`;
- `WorkspaceStrategy` как metadata-модель;
- `strategyId` в runtime plans и `.zap2` state;
- `--select-strategy`, `--list-strategies`, `--show-strategy`;
- индивидуальная передача argv в nfqws2.

Новые эквиваленты:

```bash
PYTHONPATH=gui python -m zap2_gui.app --list-presets
PYTHONPATH=gui python -m zap2_gui.app --show-preset manual-local
PYTHONPATH=gui python -m zap2_gui.app --show-preset-profile manual-local 1
PYTHONPATH=gui python -m zap2_gui.app --select-preset manual-local
```

Следующий этап может перевести runtime state с `strategyId` на `presetId`, но
только с явной миграцией старых файлов и без одновременной переделки nftables или
session lifecycle.
