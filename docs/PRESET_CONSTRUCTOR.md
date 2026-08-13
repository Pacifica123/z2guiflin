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

Конструктор изменяет и удаляет только owner-managed пресеты: созданные через
`+ Пресет` и импортированные через `Импорт .txt`. Reference/community presets
остаются read-only. Это не даёт GUI незаметно испортить проверенный исходный
файл.

Кнопка `Удалить пресет` удаляет весь owner-managed preset: canonical `.txt`,
metadata JSON и запись из `strategies/catalog.json`. Если удаляемый preset был
выбран, selection сначала переводится на `defaultStrategyId`. Общие
`presets/imported-assets/*` удаляются только когда на них больше не ссылается
другой импортированный preset. Запущенный выбранный preset удалить нельзя до
остановки Default workflow.

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
Blockcheck для domain target. Targets проверяются последовательно. Текущий
upstream run не обрывается на первой строке `AVAILABLE`: он завершается штатно,
чтобы `blockcheck2.sh` выполнил собственный firewall/NFQUEUE cleanup. После
первого target, для которого найден хотя бы один `AVAILABLE`, следующие targets
не запускаются. GUI отделяет найденные filters от action/range части и вставляет
выбранную стратегию непосредственно в текущий профиль.

`AVAILABLE` подтверждает только конкретную пару `target + probe`. Например,
результат для `www.youtube.com` по QUIC не подтверждает TCP/TLS и не покрывает
`googlevideo.com`, `ytimg.com` или другие домены сервиса. Отдельные generated
стратегии также не накапливаются при последовательном выборе: новая выбранная
стратегия заменяет предыдущую. Полный service preset обычно требует нескольких
профилей и явного списка целей.

Два стандартных `zapret-lib.lua`/`zapret-antidpi.lua` imports уже находятся на
уровне preset и при импорте не копируются. Candidate с дополнительным
`--lua-init` или `--blob` отклоняется: молча удалить такое определение означало бы
изменить найденную команду.

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
firewall redirect и выполняет cleanup. Кнопка Stop и автоматические ранние
остановки сначала посылают `SIGINT`, который upstream script обрабатывает своим
cleanup-handler. `terminate()` используется только как аварийный fallback, если
cleanup не завершился за 10 секунд.

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

## Импорт полного TXT-пресета

Кнопка `Импорт .txt` на вкладке `Пресеты` принимает внешний line-oriented
Zapret preset как полный набор ordered traffic-профилей. Импорт не выбирает и
не запускает пресет автоматически: результат становится обычным owner-managed
preset и дальше редактируется тем же конструктором.

До записи выполняется распознавание файла. Обычный `.txt` отклоняется, если в
нём нет достаточно сильной комбинации признаков Zapret: `--lua-desync`,
`--filter-*`, hostlist/ipset, `--new`, `--lua-init` и связанных параметров.
Поддерживаются UTF-8/UTF-8 BOM и CP1251. Строки конфигурации читаются как
line-oriented arguments, поэтому значения вроде `--name=Имя с пробелами`
остаются одним аргументом.

Windows Zapret2 preset адаптируется к Linux runtime:

- `--wf-*`/WinDivert capture options удаляются; nftables scope по-прежнему
  строится проектом из `--filter-tcp`/`--filter-udp` и runtime policy;
- `@lua/<file>` переписывается на существующий
  `@core/zapret2/lua/<file>`;
- `@bin/<file>` для `--blob` переписывается на существующий
  `@core/zapret2/files/fake/<file>`;
- отсутствующий Lua init можно отбросить только если все реально используемые
  `--lua-desync` functions найдены в оставшихся vendored scripts;
- отсутствующий blob definition можно отбросить только когда адаптированные
  `--lua-desync` на него не ссылаются;
- runtime-owned `--qnum`/daemon/user options не импортируются: ими управляет
  lifecycle z2guiflin;
- zapret1 `--dpi-desync*` не переводится эвристически в Zapret2 Lua и блокирует
  импорт вместо скрытого изменения стратегии.

Ссылки `hostlist`/`ipset` сохраняются без подмены. Если соответствующих файлов
нет в workspace, импорт разрешён с явным предупреждением: такой preset ещё не
готов к runtime preflight. Абсолютные пути и `..` в этих ссылках запрещены,
чтобы TXT не мог вывести чтение файлов за пределы workspace.

Metadata сохраняет имя исходного файла, SHA-256, `BuiltinVersion`/`Description`
при наличии, confidence распознавания и список выполненных адаптаций. Полный
локальный путь исходного файла в metadata не записывается.

### File dependencies импортированного TXT

Полный TXT может содержать не только параметры nfqws2, но и ссылки на внешние
`--hostlist`, `--hostlist-exclude`, `--ipset`, `--ipset-exclude`. Сам `.txt` не
содержит данные этих файлов. Поэтому наличие синтаксически корректного preset не
означает готовность к runtime.

Импортер сначала проверяет workspace, затем общий `source package root` resolver
проходит ancestors исходного файла и оценивает, от какого корня разрешается
максимум безопасных относительных ссылок. Resolver вынесен из preset adapter и
не зависит от `.txt`/Zapret: на входе у него любой source file и набор relative
resource refs. Поэтому тот же механизм можно использовать в будущих импортерах
других сущностей.

Для структуры loop-uh resolver корректно понимает логический resource root
`<repo>/src` / `<installed-root>`, где рядом ожидаются `presets/`, `lists/`,
`lua/`, `bin/`. В source checkout `zapretgui` сами runtime `lists/*.txt` могут
отсутствовать: наличие Python-модуля `src/lists` не считается наличием нужных
данных. В таком случае import остаётся неполным и GUI предлагает указать корень
установленной/распакованной runtime-поставки.

Автопоиск проходит до десяти ancestors, поэтому вложенность вида
`presets/builtin/winws2/Universal V5.txt` больше не теряет package root. Если
файлы всё равно не найдены, GUI показывает найденный root, причину/coverage и
позволяет выбрать другой корень вручную. Найденные inputs копируются в
`presets/imported-assets/txt-<digest>/...`; canonical preset ссылается уже на эти
project-owned copies. Полный путь исходного пакета в metadata не сохраняется.

Неполный preset разрешено импортировать как данные для последующего ремонта и
редактирования. В этом случае import report показывает `runtime ready after
import: no`, а metadata содержит `missingListDependencies`. Launch composer,
Overview, parser preflight и default-start считают такие ссылки blocker. В
частности, default-start проверяет их до owner-rules apply, поэтому missing list
не должен больше приводить к циклу «применить nftables -> nfqws2 exit 1 ->
rollback».

Перед реальным запуском strategy-level list/ipset files копируются во временный
public per-session input directory с безопасными правами, а соответствующие
аргументы nfqws2 переписываются на абсолютные пути этих копий. Это отделяет
runtime от прав доступа к пользовательскому workspace после privilege drop.
