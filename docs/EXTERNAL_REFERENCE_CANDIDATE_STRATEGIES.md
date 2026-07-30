# Кандидатные стратегии по внешним источникам

Статус: историческая справка Stage 7o1.

## Цель

Аудит внешних рабочих конфигураций был переведён в owner-selectable candidates. Default strategy не менялась, внешние scripts не запускались, успех Discord не объявлялся.

```text
внешняя модель capture/profile
-> безопасный кандидат z2guiflin
-> owner observation
-> общая матрица
-> продвижение только по evidence
```

## `reference-zapret2-generic-tls-fake`

Основа: upstream/vernette примеры zapret2.

```text
TCP: 80,443
HTTP: http_methodeol
TLS: fake_default_tls + tcp_ts
UDP: выключен
```

Кандидат ориентирован на случай `ESTAB`, после которого updater всё ещё не проходит первый TLS payload.

## `reference-linux-general-multisplit-like`

Основа: Linux general configs и совместимые с zapret2 `multisplit`/`multidisorder`.

```text
TCP: 80,443,2053,2083,2087,2096,8443
host bucket: profiles/hostlists/reference-general.hosts
HTTP: fake + multisplit
TLS: fake + multidisorder
UDP: выключен
```

Это широкий general candidate, но он остаётся owner-scoped и non-default.

## `reference-flowseal-simple-fake-like`

Основа: Flowseal/Sergeydigl3 simple fake branches.

```text
TCP: 80,443,2053,2083,2087,2096,8443
Discord media high TLS ports: simple fake
General host bucket: simple fake
UDP/STUN/game filter: отложены
```

## Общая граница

Все кандидаты:

- не выбираются автоматически;
- не запускаются в checks;
- используют UID-scoped nft/NFQUEUE;
- не импортируют installers/services;
- не включают voice/UDP;
- предназначены для observation matrix.

## Ручная проверка

```bash
PYTHONPATH=gui python -m zap2_gui.app \
  --select-strategy reference-linux-general-multisplit-like

sudo env PYTHONPATH=gui python -m zap2_gui.app \
  --runtime-discord-pretls-guided-probe
```

Результат является наблюдением текущей среды, а не общей оценкой стратегии.
