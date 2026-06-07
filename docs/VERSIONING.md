# Политика версионирования

## Текущая метка продукта

```text
v0.4-alpha
```

`v0.4-alpha` открывает новый цикл после owner-declared `v0.3-stable`. Предыдущая stable-точка доказала end-to-end цепочку для YouTube: Blockcheck lab нашёл `AVAILABLE` стратегии, GUI экспортировал их в `strategies/generated/`, пользователь выбрал strategy во вкладке `Стратегии`, затем Default workflow запустил `nfqws2` и это реально сработало в целевом окружении.

## Форма

Метки продукта используют формат:

```text
v<major>.<minor>-<phase>[-hf_<shortFixName>]
```

Фазы:

- `alpha` открывает цикл и может охватывать много devctl-патчей;
- `beta` означает, что цель цикла реализована достаточно для концентрированной проверки;
- `dev` означает, что владелец использует продукт для более длительного real-world testing;
- `stable` может объявить только владелец.

## Stage id для v0.3-alpha

Новый поток сбрасывает нумерацию стадий внутри продуктовой метки:

```text
v0.3-alpha_stage_1
v0.3-alpha_stage_2
v0.3-alpha_stage_3
```

Не продолжать историческую нумерацию Stage 50+. Исторические ссылки остаются валидны как old-line notes, но не как активная последовательность.

## Правила продвижения

- Ассистент не должен самостоятельно продвигать проект до `stable`.
- Не переименовывать каждый патч в новую product version.
- Использовать devctl patch id для идентичности патча и product label для идентичности вехи.
- Hotfix suffixes предназначены для `beta` и `dev`, а не для обычного `alpha` patch flow.

## Язык документации

Версионирование не меняет правило языка: вся активная проектная документация будущих патчей пишется на русском, даже если patch id, имена файлов и технические идентификаторы остаются англоязычными.

## Переход Stage 14 к v0.3-beta

После `v0.3-alpha_stage_14` продуктовая метка становится `v0.3-beta`, потому что alpha-цепочка controlled runtime lifecycle закрыта: есть профили/стратегии, runtime contracts, plan generator, state/log/confirmation gate, session runner, owner-confirmed apply/revert, service plans и default start/stop workflow.

Дальнейшие патчи должны именоваться от `v0.3-beta`, если они не являются срочными hotfix-патчами к уже выпущенному Stage 14.

## Переход v0.3-beta → v0.3-dev

`v0.3-beta` зафиксировала контролируемую runtime baseline: build, plan,
confirmation, apply/revert, session и GUI toggle. `v0.3-dev` — следующий
разработческий цикл поверх этой базы. Его первая цель — не расширять поверхность,
а стабилизировать запуск: корректный devctl patch format, чистое дерево
инструментов и более безопасный NFQUEUE scope.

## Сброс нумерации внутри v0.3-dev

Переходные патчи, которые перевели ветку к `v0.3-dev` и исправили старт после
safer interception, исторически назывались Stage 16/17, потому что продолжали
предыдущую beta-цепочку. Начиная с GUI Blockcheck lab, dev-цикл нумеруется
заново:

```text
v0.3-dev_stage_1
v0.3-dev_stage_2
v0.3-dev_stage_3
v0.3-dev_stage_4
v0.3-dev_stage_5
```

Это не меняет продуктовую метку `v0.3-dev`, но делает следующие dev-патчи
читабельными и отделяет новый цикл от закрытого alpha/beta runtime baseline.

## v0.3-dev Stage 2

`v0.3-dev_stage_2` продолжает новый dev-цикл после Blockcheck lab и добавляет
локальную сборку prerequisites для него: `nfqws2` и `mdig` больше не должны
обнаруживаться только после запуска privileged upstream script. Номер Stage 2
подтверждает сброшенную dev-нумерацию и не возвращается к историческим Stage
16/17.

## v0.3-dev Stage 4

`v0.3-dev_stage_4` продолжает Blockcheck lab и исправляет запуск upstream
`blockcheck2.sh` в пользовательском workspace: GUI wrapper теперь передаёт
`WS_UID/WS_GID` владельца, чтобы `nfqws2` после privilege drop мог читать
`core/zapret2/lua/*.lua`. Номер Stage 4 остаётся внутри сброшенного dev-цикла.


## v0.3-dev Stage 5

`v0.3-dev_stage_5` продолжает Blockcheck lab без изменения продуктовой метки.
Stage 5 не добавляет автоматических эвристик ранней остановки и не меняет
privileged boundary; он только сохраняет краткую статистику по уже увиденному
выводу blockcheck после Stop или finish. Это помогает анализировать длинные
прогоны, где большинство candidate strategies завершается одинаковой ошибкой,
например `curl code 28: connection timed out`.

## v0.3-dev Stage 6

`v0.3-dev_stage_6` продолжает Blockcheck lab и замыкает первую полноценную
пользовательскую петлю подбора стратегии: available results из blockcheck можно
экспортировать в `strategies/generated/`, увидеть во вкладке `Стратегии`, выбрать
одну из них для Default profile и затем заново пройти обычный plan/confirmation
путь запуска. Номер Stage 6 остаётся внутри сброшенного dev-цикла.

## v0.3-dev Stage 7

`v0.3-dev_stage_7` продолжает Blockcheck lab без изменения продуктовой метки. Основной смысл stage — evidence-based управление долгими blockcheck-запусками: sequential candidates, автоматический skip target с мёртвым TCP/443 port precheck и экспорт только из последнего successful blockcheck source.

## Переход v0.3-dev → v0.3-stable

После `v0.3-dev_stage_7` владелец проекта забэкапировал состояние как `v0.3-stable`. Это решение принимает владелец, а не ассистент. Смысл stable-точки:

- Blockcheck lab умеет реально прогонять upstream `blockcheck2.sh` без заморозки GUI;
- prerequisites для `nfqws2`/`mdig` собираются локально и явно;
- долгие прогоны имеют live log, Stop и краткую статистику;
- sequential candidates не тратят scan на target с мёртвым TCP/443 precheck;
- найденные `AVAILABLE` стратегии экспортируются в `strategies/generated/`;
- стратегия выбирается во вкладке `Стратегии`;
- Default workflow строится по выбранной strategy id и запускается через owner-confirmed sudo-askpass путь;
- в целевом окружении владельца это уже сработало как минимум для YouTube.

## Переход v0.3-stable → v0.4-alpha

`v0.4-alpha` начинается не с переписывания runtime, а с расширения доказанной цепочки на новый сервис: desktop Discord. Цель цикла — подобрать рабочий набор target domains/probes для desktop Discord, получить generated strategy, выбрать её и проверить запуск через существующий Default workflow.

В рамках `v0.4-*` сознательно не решается задача автоматической композиции нескольких сервисов в одну универсальную стратегию. Допустимый UX для этого цикла:

```text
выбрать стратегию YouTube
или
выбрать стратегию Discord
```

но не обязательно:

```text
автоматически совместить YouTube + Discord без конфликтов
```

## Сброс нумерации внутри v0.4-alpha

Переход на `v0.4-alpha` снова сбрасывает stage-нумерацию. Этот документационный baseline считается `v0.4-alpha_stage_0`, чтобы зафиксировать новую цель и не смешивать её с закрытым `v0.3-dev` loop. Следующие реализационные патчи должны начинаться с:

```text
v0.4-alpha_stage_1
v0.4-alpha_stage_2
v0.4-alpha_stage_3
```

Stage id должен описывать конкретный шаг Discord desktop cycle, например candidate discovery, Discord Blockcheck preset, strategy export UX или runtime verification.

