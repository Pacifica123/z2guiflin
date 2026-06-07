# План v0.4-alpha: desktop Discord

`v0.4-alpha` открывает цикл после owner-declared `v0.3-stable`. Предыдущая веха доказала, что проект уже может провести пользователя по цепочке:

```text
Blockcheck lab -> AVAILABLE strategies -> generated strategy files -> выбор стратегии -> Default workflow -> рабочий YouTube
```

Цель `v0.4-*` — повторить эту цепочку для desktop-версии Discord.

## Исходная позиция

На момент открытия `v0.4-alpha` уже есть:

- vendored `zapret2` в `core/zapret2/`;
- локальная сборка `nfqws2` и `mdig` через owner-controlled build path;
- live Blockcheck lab без заморозки GUI;
- статистика длинных прогонов;
- sequential target candidates и dead-target guard;
- экспорт `AVAILABLE` стратегий в `strategies/generated/`;
- вкладка `Стратегии` с выбором active strategy для Default profile;
- owner-confirmed Default workflow через plan/hash/confirmation/sudo-askpass.

## Цель цикла

Минимальная полезная цель `v0.4-alpha`:

1. подобрать candidate targets для desktop Discord;
2. прогнать их через Blockcheck lab без бессмысленного зависания на мёртвом target;
3. получить хотя бы одну generated strategy для Discord;
4. выбрать её во вкладке `Стратегии`;
5. запустить Default workflow;
6. проверить, что desktop Discord оживает в окружении владельца.

## Нефокус v0.4

Для `v0.4-*` сознательно откладывается задача автоматического объединения стратегий нескольких сервисов. Допустимый пользовательский сценарий:

```text
выбрать YouTube strategy
или
выбрать Discord strategy
```

Недопустимо тратить цикл на обязательное решение задачи:

```text
автоматически совместить YouTube + Discord + будущие сервисы в одну универсальную стратегию
```

Такое объединение лучше делать позже, когда будут понятны реальные Discord probes, порты, протоколы и конфликты `nfqws2` аргументов.

## Методология

Для Discord не нужно сразу добавлять скрытый «магический режим». Предпочтительный путь:

- явно показывать candidate targets владельцу;
- сохранять live output и successful source logs;
- экспортировать Discord strategies с service-aware именами;
- сохранять возможность открыть JSON и увидеть исходную `nfqws2` строку;
- не менять firewall/service state без того же owner-confirmed workflow, который уже используется для YouTube.

## Признаки готовности к v0.4-beta

`v0.4-alpha` можно считать готовой к переходу в beta, когда владелец сможет сказать:

- GUI предложил или позволил задать осмысленные Discord targets;
- Blockcheck нашёл применимую стратегию для одного из них;
- стратегия экспортировалась в `strategies/generated/`;
- стратегия была выбрана во вкладке `Стратегии`;
- Default workflow стартовал без регресса safety boundary;
- desktop Discord реально заработал хотя бы в базовом сценарии владельца.
