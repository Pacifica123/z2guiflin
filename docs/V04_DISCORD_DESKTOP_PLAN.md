# Исторический план desktop Discord для v0.4

Статус: архив первоначальной продуктовой цели.

## Исходная позиция

v0.3 доказала цепочку Blockcheck -> generated strategy -> Default workflow на YouTube. План v0.4 пытался применить ту же модель к desktop Discord без преждевременного универсального объединения сервисов.

## Первоначальная цель

Владелец должен был уметь:

- выбрать `discord-desktop`;
- проверить updater/app/gateway/CDN targets;
- экспортировать strategy;
- выбрать её;
- запустить Default workflow;
- проверить Discord non-voice.

Voice/UDP, автоматическая композиция и tunnel routing сначала не входили в критерий.

## Что выяснилось

Desktop Discord не является одной HTTPS-целью. Отказ мог находиться на разных уровнях:

```text
DNS
TCP SYN/SYN+ACK
TLS ClientHello/ServerHello
updater HTTPS
webapp/API/gateway
Electron/Flatpak proxy route
voice/media UDP
```

Поэтому проект добавил endpoint discovery, DNS edge check, pre-TLS counters, observation matrix, HAR и tunnel lane.

## Изменение трактовки

В ходе owner tests часть стратегий помогала YouTube, часть переводила Discord на следующий этап, часть помогала сообщениям/запуску, а часть не давала устойчивого preset даже для YouTube.

Это показало, что итоговый критерий «Discord обязан быть починен одной стратегией» некорректен для версии приложения.

## Текущий итог

План завершён выпуском v0.4 как диагностической/runtime-платформы. Конкретные Discord стратегии остаются owner-observed candidates, а не гарантией продукта.
