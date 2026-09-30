# Результаты community edge-flow для Discord

Статус: ретроспектива экспериментов Stage 7j–7w.

## Основной вывод

Стратегия `community-discord-youtube-edge-flow` показала важное разделение:

- YouTube изменял поведение на том же Linux runtime;
- desktop Discord оставался на `Checking for updates`;
- endpoint discovery показывал Discord Cloudflare sockets в `SYN-SENT`.

Следовательно, общая цепочка `nftables -> NFQUEUE -> nfqws2 -> strategy selection` работала достаточно, чтобы влиять на YouTube. Оставшийся отказ Discord находился в более ранней или иной части потока.

## Вариант v2

Была добавлена стратегия:

```text
community-discord-syndata-edge-flow-v2
```

Её ранние ветки проверяли:

```text
payload=empty + out-range=<s1 + send:tcp_md5
out-range=s1<d1 + syndata:blob=fake_default_tls
```

Они применялись к наблюдаемым Cloudflare edge IP, после чего шли host-based Discord и YouTube профили.

## Как читался результат

Положительный признак:

```text
SYN-SENT -> ESTAB -> TLS/HTTP progress
```

Отрицательный признак:

```text
тот же edge остаётся в SYN-SENT
```

При отрицательном результате нужно проверять hook/capture scope и попадание SYN в NFQUEUE, а не добавлять очередную TLS-only стратегию.

## Исправление args-file

Аргументы с `<`, например `--out-range=<s1`, должны записываться в `@args` с безопасным quoting. Иначе upstream `wordexp(3)` разбирает их неверно. Одновременно временный каталог runtime inputs был сделан UID-scoped, чтобы stale root-owned файлы не ломали проверки.

## Вариант с TCP 5222

`community-discord-hostfakesplit-5222-minimal` проверял более широкий Discord capture envelope отдельно от YouTube fallback.

## Вариант v2b

После перехода соединения в `ESTAB` наблюдался `ERR_TIMED_OUT` после TLS ClientHello к `discordapp.com`. В `community-discord-syndata-edge-flow-v2b` были добавлены:

```text
discordapp.com
www.discordapp.com
```

Это проверяло, является ли следующий blocker простой нехваткой host coverage.

## Матрица v2c

Когда v2b не дал однозначного результата, были созданы четыре owner-selected варианта:

```text
community-discord-syndata-edge-flow-v2c-send-only
community-discord-syndata-edge-flow-v2c-fixed-sni
community-discord-syndata-edge-flow-v2c-no-md5
community-discord-syndata-edge-flow-v2c-host-first
```

Они изолировали влияние `syndata`, `rndsni`, `tcp_md5` и порядка hostlist/edge-IP профилей.

## Текущая актуальность

Эти стратегии остаются кандидатами и историческими инструментами сравнения. Наличие в каталоге не означает, что они подходят текущей сети. В v0.4 результат трактуется как owner observation.
