# P01: Network truth — VLESS / Vesktop

Статус: контракт реализован для tunnel lane. Реальная поддержка конкретного remote route/Vesktop не объявляется без evidence текущего запуска.

## Главный принцип

Локальные признаки разделены и **не повышаются** автоматически до remote/application success:

```text
process
  -> listener
  -> socks_method
  -> socks_connect(target)
  -> target_tls(target)
  -> target_http(target)
```

Это не универсальная линейная state machine. Это удобная проекция отдельных `ProbeSpan`; для Vesktop дополнительно нужны независимые application spans (Gateway WebSocket и main-window navigation). Каждый failed span также несёт типизированный `failureClass` (`socks_connect`, `target_tls_timeout`, `target_tls_eof_or_reset`, `target_http`, `electron_navigation` и т. п.), чтобы диагноз не сводился к одному текстовому сообщению.

Пример: `process=PASS + listener=PASS + socks_method=PASS`, но `target_tls=FAIL` означает, что локальный SOCKS работает, однако HTTPS route к этому target имеет `UNSUPPORTED` для текущего run. UI/CLI не имеет права показывать общий green-ready.

## Run-bound evidence

Каждый запуск tunnel core получает новый `runId`. `EvidenceGraph/v1` привязан к:

- `runId`;
- `connectionReceiptId`;
- `coreIdentityHash`;
- `configHash`;
- target и environment конкретных spans.

Старые PASS не удовлетворяют capability нового запуска. Evaluator учитывает только evidence текущего `runId`; найденные stale refs могут быть показаны как ignored. Кроме `runId`, при чтении current evidence повторно сверяются `connectionId`, `connectionReceiptId`, `configHash` и `coreIdentityHash`. Несовпадение хотя бы одной привязки переводит current capability в `UNKNOWN` вместо использования потенциально устаревшего PASS.

Файлы runtime/evidence находятся под `.zap2/tunnel/` и являются локальным состоянием, а не частью исходников проекта.

## ConnectionReceipt/v2 и семантика VLESS

При импорте сохраняется redacted `ConnectionReceipt/v2`:

- hash исходного URI, но не сам URI;
- normalized hash;
- имена распознанных query keys;
- имена неизвестных query keys;
- redacted connection summary (включая hash/presence вместо UUID, remarks, transport path/service name и других потенциально чувствительных значений);
- `sourceSemanticHash`, `generatedSemanticHash` и `semanticDiff`;
- semantic-generation verdict для выбранного core lane.

Повторяющиеся query keys отклоняются при импорте: их нельзя тихо схлопнуть в `dict`, потому что это могло бы изменить смысл URI. Для `SUPPORTED/full` недостаточно просто «узнать имя параметра» — каноническая семантика source и generated config должна совпасть без required-loss.

Правила support:

| Generation state | Значение |
|---|---|
| `SUPPORTED / full` | все распознанные обязательные семантики представлены генератором, source provenance доступен |
| `EXPERIMENTAL / partial` | известные семантики представлены, но есть неизвестные query keys или исторически нет source hash |
| `UNSUPPORTED / loss` | обязательная распознанная семантика теряется; start блокируется |

Xray и V2Ray имеют отдельные generator capability scopes. Совпадение слова `VLESS` не означает одинаковую поддержку transport/security/schema.

## CoreCapability

Preflight/runtime фиксируют core identity и scope:

```text
kind
version (когда безопасно/уместно получить)
binarySha256
identityHash
configHash
configTest
supportedFields
supportedTransports
supportedSecurity
```

`configTest=PASS` относится только к конкретной конфигурации и конкретному binary. Generator-declared scope сам по себе не доказывает remote network success.

## CapabilityVerdict

Основные capability:

- `route.https:updates.discord.com`;
- `route.https:discord.com`;
- `discord.bootstrap.gateway`;
- `vesktop.navigation`;
- aggregate `vesktop.bootstrap`.

`vesktop.bootstrap=SUPPORTED` возможен только когда **все обязательные current-run predicates PASS**. Если обязательный predicate упал — aggregate `UNSUPPORTED`; если evidence отсутствует/UNKNOWN — aggregate `UNKNOWN`.

Voice/media в P01 не считаются обязательными, пока они отдельно не рекламируются как поддерживаемая capability.

## CLI / GUI

```bash
PYTHONPATH=gui python -m zap2_gui.app --discord-tunnel-probe
PYTHONPATH=gui python -m zap2_gui.app --discord-tunnel-https-probe
# контрольный neutral target можно задать отдельно, например:
PYTHONPATH=gui python -m zap2_gui.app --discord-tunnel-https-probe --tunnel-probe-host example.com
PYTHONPATH=gui python -m zap2_gui.app --discord-tunnel-evidence
PYTHONPATH=gui python -m zap2_gui.app --discord-tunnel-route-diagnose
```

`--discord-tunnel-evidence` показывает current-run spans, capability verdicts, missing/failed predicates и следующий полезный experiment.

В GUI во вкладке tunnel добавлена кнопка **Evidence / capability**.

`route-diagnose` сохраняет старые диагностические эвристики по логам, но явно маркирует их как неавторитетные для `CapabilityVerdict`.

## Failed-preflight bypass

`--discord-launch-allow-failed-preflight` разрешает владельцу провести ручной эксперимент, но **не меняет verdict**. В session/report записывается `bypassChangesVerdict=false`.

Таким образом, override может изменить действие (launch), но не может превратить TLS FAIL/UNKNOWN в green capability.

## SOCKS containment

Текущий локальный SOCKS lane:

- bind: loopback `127.0.0.1`;
- auth: `noauth`;
- UDP: выключен в generated inbound;
- app access: явные proxy env/Chromium flags;
- случайный/нестандартный port **не является authentication**.

Это containment для локального desktop процесса, а не сетевой security boundary для недоверенных локальных пользователей.

## Vesktop: что доказано и что ещё нет

Автоматические offline tests доказывают contracts, redaction, stale-evidence rejection, semantic-loss blocking, proxy argv composition и bypass invariant.

Они **не доказывают**, что конкретный пользовательский VLESS server сейчас пропускает Discord/Vesktop. Для такого утверждения нужны live E1–E8 evidence из текущей среды. В частности, пока нет current-run Gateway WebSocket и Vesktop main-window navigation evidence, `vesktop.bootstrap` остаётся `UNKNOWN` даже при успешном HTTPS probe.

Persistent Chromium netlog по умолчанию не включается: это осознанно, чтобы не сохранять объёмный потенциально чувствительный debug trace. При необходимости он должен быть временным owner experiment с redaction/cleanup.

## Troubleshooting по первому failing predicate

| Evidence | Интерпретация | Следующий эксперимент |
|---|---|---|
| process FAIL | core не жив | stderr/config/core preflight |
| listener FAIL | нет TCP listener | bind/port/process evidence |
| socks_method FAIL | порт не является ожидаемым SOCKS5/noauth | проверить owner процесса/config inbound |
| socks_connect FAIL | SOCKS не смог установить target CONNECT | correlated core route/server diagnostics |
| target_tls FAIL | CONNECT есть, TLS к target не завершён; `failureClass` уточняет EOF/reset/timeout/validation | сравнить neutral и Discord target; затем correlated remote/core evidence |
| target_http FAIL | TLS есть, HTTP semantics не подтверждены | status/headers/redirect/application endpoint evidence |
| Gateway UNKNOWN/FAIL | bootstrap WebSocket не подтверждён | current-run WebSocket experiment |
| navigation UNKNOWN/FAIL | окно Vesktop не подтверждено | managed launch + owner/main-frame evidence |

Не следует менять несколько transport/security/browser параметров одновременно: P01 требует сначала локализовать failing predicate, затем менять только доказанную причину.
