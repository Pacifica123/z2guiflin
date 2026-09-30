# Универсальный HAR workbench — v0.4-alpha Stage 8e

Stage 8e исправляет неверную границу Stage 8d: HAR относится не к Discord, а к
любому browser-visible ресурсу. Один и тот же импорт должен работать для
YouTube, Discord, GitHub, CDN, web-приложения или другого сайта.

Discord Voice остаётся отдельной задачей. Его UDP media-flow не появляется в
обычном HAR и не добавляется в универсальные HAR-группы.

## Цепочка

```text
HAR import
  -> безопасный разбор
  -> точные hostnames и обезличенные ошибки
  -> сравнение со всеми profiles/hostlists/*.hosts
  -> группировка по domain family + L7 + причине
  -> targets.txt и blockcheck-options.json
  -> owner-confirmed Blockcheck
  -> выбор стратегии для группы
  -> preset blueprint
```

Новые CLI-команды:

```bash
PYTHONPATH=gui python -m zap2_gui.app --har-plan
PYTHONPATH=gui python -m zap2_gui.app --har-analyze /path/to/capture.har
PYTHONPATH=gui python -m zap2_gui.app --har-report
PYTHONPATH=gui python -m zap2_gui.app --har-workbench /path/to/capture.har
PYTHONPATH=gui python -m zap2_gui.app --har-workbench-report
PYTHONPATH=gui python -m zap2_gui.app --har-group-plan GROUP_ID
```

Старые `--discord-har-*` сохранены как отдельная legacy-цепочка, чтобы не ломать
старые отчёты и тесты. GUI Blockcheck Lab использует новую универсальную цепочку.

## Пример YouTube

Допустим, HAR содержит:

```text
rr8---sn-n8v7znlr.googlevideo.com
status=0
error=NS_BINDING_ABORTED
HTTP/2
```

Парсер сохраняет точный hostname и безопасный код ошибки, но выбрасывает query,
токены и raw error detail. Domain family будет `googlevideo.com`.

Результат может выглядеть так:

```text
har-googlevideo-com-tls-browser-cancelled
family: googlevideo.com
targets: rr8---sn-n8v7znlr.googlevideo.com
coverage: covered by default.hosts
```

Точный `rr8---...` остаётся целью Blockcheck. `googlevideo.com` используется как
метка группы и не заменяет точную цель автоматически.

Так как `googlevideo.com` уже есть в `default.hosts`, вывод будет не «добавить
ещё один домен», а «hostlist уже покрывает hostname; проверить стратегию и L7».

## Какие группы создаются

Группа строится по трём признакам:

1. Domain family, например `googlevideo.com`.
2. L7, который реально виден в HAR: `http`, `tls`, `websocket`, `quic`.
3. Причина внимания:
   - `transport-failure`;
   - `browser-cancelled`;
   - `http-server-error`;
   - `http-client-error`;
   - `uncovered-observed`.

Один успешный и уже покрытый host не создаёт отдельную группу. Он остаётся в
sanitized summary. Группа создаётся, когда есть ошибка или host отсутствует во
всех локальных hostlists.

## Ошибки

Raw error text не сохраняется. Из него извлекаются только безопасные коды вроде:

- `NS_BINDING_ABORTED`;
- `ERR_CONNECTION_RESET`;
- `ERR_QUIC_PROTOCOL_ERROR`;
- `SEC_ERROR_*`.

`NS_BINDING_ABORTED` и `ERR_ABORTED` относятся к `browser-cancelled`. Такая
отмена может быть нормальной: браузер прекратил загрузку segment, сменил quality
или ушёл со страницы. Поэтому один такой случай не считается доказательством
DPI. Повторы повышают приоритет, но всё равно требуют Blockcheck и ручной
проверки.

HTTP `4xx` тоже не считается прямым доказательством блокировки: сервер уже
ответил. HTTP `5xx` может быть проблемой самого сервиса.

## Hostlist-кандидаты

Workbench разделяет:

- `attentionCoveredHosts` — host падает, но уже покрыт hostlist;
- `attentionUncoveredHosts` — host падает и не покрыт;
- `observedUncoveredHosts` — новый host замечен, но явной ошибки нет.

Кандидаты пишутся в `hostlist-candidates.txt`, но не добавляются автоматически.
Для динамических CDN-хостов family suffix предлагается только как кандидат на
review. Точные hosts всегда сохраняются отдельно.

## Граница HAR

HAR хорошо видит HTTP, HTTPS/TLS, WebSocket и иногда HTTP/3/QUIC. Он не является
packet capture.

Из HAR нельзя надёжно получить:

- произвольный TCP/UDP поток вне browser request;
- Discord Voice RTP/STUN/UDP;
- реальные nftables/NFQUEUE признаки;
- точный момент DPI-вмешательства до HTTP-уровня.

Поэтому HAR создаёт доказательства и группы, а не готовую стратегию. Blockcheck
остаётся отдельным подтверждаемым шагом.
