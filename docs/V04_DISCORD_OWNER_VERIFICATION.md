# Историческая owner-проверка Discord non-voice

Статус: архив Stage 6–7d. Для текущей проверки использовать инструменты GUI, observation matrix и `PROJECT_STATUS.md`.

## Граница

Проверялись:

- запуск desktop Discord;
- прохождение updater/bootstrap;
- загрузка app/API;
- gateway/messages;
- CDN/media на non-voice уровне.

Voice/STUN не считались обязательными.

## Базовый цикл

```text
полностью закрыть Discord
-> выбрать service target/strategy
-> запустить owner-confirmed Default workflow
-> открыть Discord
-> зафиксировать updater/app/gateway результат
-> сохранить endpoints/logs
-> остановить workflow
```

## Что записывалось

- выбранный preset/strategy;
- coverage targets;
- build/runtime state;
- endpoint states;
- ошибки updater/app;
- отличие от baseline;
- влияние на YouTube;
- необходимость следующего target/strategy experiment.

## Переход к failure-driven диагностике

После первых проверок успех `discord.com` перестал считаться достаточным. Были добавлены updater targets, phase-aware tournament, port precheck и отдельные per-target logs.

Когда sockets оставались в `SYN-SENT`, проверка была перенесена на endpoint/DNS/pre-TLS слой. Когда появлялся `ESTAB`, исследование переходило к TLS/host coverage и порядку профилей.

## Текущая актуальность

Шаблон остаётся полезен как дисциплина owner observation. Он не является критерием версии v0.4 и не гарантирует воспроизводимость на другой сети.
