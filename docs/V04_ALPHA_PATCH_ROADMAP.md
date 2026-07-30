# Историческая дорожная карта v0.4-alpha

Статус: архив завершённого цикла. Текущая граница релиза описана в `V04_RELEASE.md`.

## Исходная цель

Первоначально v0.4 формулировалась как цикл desktop Discord поверх рабочей YouTube-цепочки v0.3:

```text
service target
-> Blockcheck
-> generated strategy
-> selection
-> Default workflow
-> owner verification
```

На раннем этапе допускался выбор одной целевой стратегии: `youtube-basic`, `discord-desktop` или `custom`. Одновременная работа YouTube и Discord не являлась критерием готовности.

## Основные этапы

### Service targets

Был создан registry целей для YouTube, Discord и custom targets. Discord seed включал updater, app/API, gateway, CDN/media и secondary hosts.

### Hostlist/runtime alignment

`discord-desktop` targets были выровнены с `profiles/hostlists/default.hosts`, а тесты начали ловить дрейф между диагностикой и runtime.

### Service-aware export

Generated strategy получила coverage metadata. Успех одного домена перестал считаться доказательством всего desktop workflow.

### Failure-driven coverage

Добавлены phase-aware targets, target scan и сохранение per-target logs.

### Endpoint/DNS/pre-TLS

Когда updater зависал до TLS, проект перешёл от угадывания hosts к:

```text
endpoint watch
TCP state/timer
DNS edge check
nft/NFQUEUE counters
pktdebug strategy
guided pre-TLS probe
```

### External reference matrix

Идеи bol-van, Linux configs, loop-uh и Flowseal были переведены в безопасные candidates и общую observation matrix.

### SOCKS5/VLESS

Добавлена независимая tunnel lane с внешним core, redacted profile, probes, launch wrapper и route diagnosis.

### HAR

Discord HAR инструмент был обобщён до универсального HAR workbench для любого ресурса. Отдельно добавлены Discord Voice source candidates.

### GUI

В конце цикла были исправлены launcher, layout, tabs, controls и светлая/тёмная тема.

## Почему roadmap закрыт

Цикл достиг зрелой платформы, но не универсального сетевого результата. Некоторые стратегии помогают YouTube и Discord, некоторые не собираются в рабочий preset даже для YouTube. Это зависит от DPI и среды, поэтому не должно бесконечно удерживать продукт в `alpha`.

## Итог

Состояние Stage 8f-r3 принято как `v0.4`. Следующие задачи берутся из `KNOWN_GAPS_CHECKLISTS.md`, а не продолжают эту stage-нумерацию.
