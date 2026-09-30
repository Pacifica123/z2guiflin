# Аудит внешних reference-проектов

Статус: ретроспектива Stage 7o0 с актуальными выводами для v0.4.

## Исследованные источники

В локальный audit входили предоставленные снимки:

```text
zapret2 core от bol-van
Windows GUI от loop-uh
Flowseal zapret-discord-youtube
несколько Linux configuration packs
```

Сводка хранится в:

```text
references/external/stage7o0_external_reference_audit.json
references/external/snippets/
```

## Главный вывод

Рабочие внешние варианты обычно состоят из двух отдельных слоёв:

```text
capture envelope
-> ordered strategy/profile family
```

Нельзя переносить только список доменов или только одну desync-функцию.

## Область перехвата

Во внешних конфигурациях часто встречаются:

```text
TCP: 80,443 и дополнительные 2053,2083,2087,2096,8443
UDP: 443, STUN, Discord media и игровые ranges
более широкие packet windows
общие hostlist/ipset buckets
```

Широкий envelope не должен становиться default без owner-visible preview и оценки побочных эффектов.

## Профили и стратегии

Часто используются:

```text
fake TLS
multisplit / multidisorder
fake QUIC
hostlist / ipset
отдельные Discord media/STUN ветки
```

Windows `WinDivert --wf-*` и zapret1 `--dpi-desync-*` не являются Linux `nfqws2` options. Переносятся идеи и порядок, а не команды.

## Сравнение подходов

### bol-van

Сильные стороны: полноценное ядро, строгая модель профилей, `blockcheck2`, Linux interception и богатая документация. Недостаток для конечного пользователя: это не GUI-продукт под конкретный desktop workflow.

### loop-uh

Сильные стороны: зрелый preset UX, live orchestrator, DNS, updater, autostart, tray и process lifecycle. Ограничение для z2guiflin: архитектура Windows/WinDivert не переносится напрямую.

### Flowseal

Сильные стороны: много готовых стратегий, service workflow и простые списки host/ipset. Ограничение: стратегия подбирается перебором, а Windows bundle скрывает часть различий Linux capture/runtime.

### z2guiflin

Сильные стороны: Arch/Linux фокус, owner confirmation, подробные reports, HAR, observation matrix и явное разделение runtime/tunnel. Недостатки собраны в `KNOWN_GAPS_CHECKLISTS.md`.

## Безопасная граница

Аудит запрещает:

- запускать чужие installers/scripts;
- копировать широкие firewall rules как default;
- переводить WinDivert flags механически;
- менять default strategy без owner evidence;
- считать внешний working preset доказательством для текущей сети.
