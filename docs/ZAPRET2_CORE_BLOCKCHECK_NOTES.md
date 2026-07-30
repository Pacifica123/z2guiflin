# Заметки по ядру zapret2 для Blockcheck

Статус: справка по выводам v0.4.

## Custom lists blockcheck2

Upstream `blockcheck2.d/custom/README.txt` позволяет переопределять списки стратегий через:

```text
LIST_HTTP
LIST_HTTPS_TLS12
LIST_HTTPS_TLS13
LIST_QUIC
```

Это безопасная основа для one-strategy tournament: записать один candidate в временный list и проверить его по нужным фазам, а не собирать большой несвязанный набор.

## Порядок профилей

`nfqws2` выбирает первый подходящий профиль. Часть признаков, например L7/hostlist, может стать известна позднее, после чего возможен profile rediscovery.

Следствие: updater/app/gateway/CDN/voice нельзя собирать случайным набором широких веток. Порядок и filters должны быть явными. Ранний широкий TCP 443 профиль способен перекрыть более точный media/updater профиль.

## Граница Windows reference

Flowseal и Windows GUI полезны как источники идей, но используют WinDivert и zapret1-style options. Linux surface:

```text
nfqws2
Lua --lua-desync
protocol filters
hostlists/ipsets
nftables NFQUEUE
```

Концептуальные соответствия `fake`, `fakedsplit`, `multisplit` и других функций проверяются через zapret2, а не копируются слепо.

## Практические выводы

- Discord media может использовать TCP 2053/2083/2087/2096/8443.
- UDP/voice является отдельным STUN/Discord L7 слоем.
- TLS strategy не проверяется, если socket не прошёл TCP connect.
- Endpoint discovery должен предшествовать добавлению guessed hosts.
- HAR полезен после HTTP-уровня, но не заменяет pre-TLS counters.
- DNS edge check не должен менять системный DNS автоматически.
