# Конструктор пресетов

## Кратко

Вкладка `Пресеты` теперь умеет создавать отдельные owner-managed пресеты и
редактировать их traffic-профили.

Рабочая схема:

```text
пресет
  -> профиль 1: filter + target + strategy
  -> профиль 2: filter + target + strategy
  -> профиль N: filter + target + strategy
```

Порядок является частью конфигурации. `nfqws2` проверяет профили сверху вниз,
поэтому более узкий профиль обычно должен находиться выше широкого fallback.
Кнопки `↑` и `↓` меняют этот порядок в canonical preset-файле.

## Создание

Кнопка `+ Пресет` создаёт:

```text
presets/workspace/<preset-id>.txt
strategies/workspace/<preset-id>.json
```

`.txt` является исполнимым источником параметров `nfqws2`. JSON хранит
метаданные и контрольную копию `runtimeArgs`. Путь JSON добавляется в
`strategies/catalog.json`.

Конструктор изменяет только пресеты, которые сам создал. Reference, community,
imported и generated пресеты остаются read-only. Это не даёт GUI незаметно
испортить проверенный исходный файл.

## Профиль

Кнопка `+ Профиль` открывает редактор со следующими полями:

```text
name
protocol: TCP / UDP / any
ports
filter-l3
filter-l7
target type
target value
strategy
```

Поддерживаемые targets:

- domains/URI -> `--hostlist-domains`;
- hostlist file -> `--hostlist`;
- inline IP/CIDR -> `--ipset-ip`;
- ipset file -> `--ipset`;
- no target — только когда остальные filters достаточно узкие.

Профиль без protocol, L3, L7 и target запрещён: он перехватил бы весь трафик.

## Три источника стратегии

### Известная стратегия

GUI извлекает action/range часть из уже существующих профилей. Filter, target,
`--lua-init`, `--new` и имя исходного профиля не копируются. Новый профиль
получает только reusable `payload`, `range`, `lua-desync` и связанные action
options.

### Ручные nfqws2 args

Ручное поле принимает profile-level action options. Оно не принимает глобальные
или filter-аргументы. В частности запрещены:

```text
--new
--lua-init
--filter-*
--hostlist*
--ipset*
--name
```

Стратегия должна содержать хотя бы один `--lua-desync`.

### Blockcheck

Кнопка `Подобрать Blockcheck и вставить` запускает существующий compact
Blockcheck для domain target. Targets проверяются последовательно. После первого
`AVAILABLE` GUI отделяет найденные filters от action/range части и вставляет
стратегию непосредственно в текущий профиль.

Этот путь подходит для domain HTTP/TLS и QUIC/HTTP3. Он не выдаёт корректный
ответ для Discord Voice/STUN UDP. Для voice-профиля пока используются известная
или ручная стратегия. Отдельный voice probe должен быть отдельной диагностикой,
а не маскироваться под обычный Blockcheck.

## Безопасность

Создание и редактирование не запускают `nfqws2`, не меняют nftables, NFQUEUE,
systemd или сервисы.

Выбранный и реально запущенный preset нельзя изменить до остановки Default
workflow. После любого изменения `runtimeArgs` ранее подготовленный start-plan
считается устаревшим: preset нужно выбрать, затем заново создать и подтвердить
plan.

Blockcheck является отдельным исключением: он запускается только после явного
подтверждения, использует существующий `sudo -A` путь, временно меняет свой
firewall redirect и выполняет cleanup.

## Пример порядка

```text
1. Discord Voice
   UDP 50000-65535
   L7: stun,discord
   target: none или узкий ipset

2. YouTube QUIC
   UDP 443
   L7: quic
   target: youtube.com и связанные домены

3. Discord / YouTube TLS fallback
   TCP 443
   L7: tls
   target: явный список доменов
```

Это только пример структуры. Конкретные ports, L7 и стратегия должны
подтверждаться диагностикой на текущей сети.
