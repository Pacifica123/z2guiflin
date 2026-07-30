# Перенос идей Windows community preset

Статус: историческая справка Stage 7j.

## Исходное наблюдение

Пользовательский Windows preset помогал YouTube и Discord в похожей сети, тогда как Linux `discord-desktop` путь оставался на timeout/SYN-SENT.

## Полезные идеи

- широкий capture envelope;
- `--ipcache-hostname=1`;
- отдельные updater/app/CDN профили;
- `hostfakesplit_multi` для Discord hosts;
- сочетание TCP split/disorder и UDP QUIC fake для YouTube;
- отдельные media/high TLS ports.

## Ограничение перевода

Linux runtime использует `nftables` + NFQUEUE + `nfqws2`. Поэтому:

- `--wf-*` не копируются в `runtimeArgs`;
- ports переводятся в `capturePolicy`/`--filter-tcp`/`--filter-udp`;
- zapret1-style flags заменяются на Lua primitives zapret2;
- широкий Windows filter не становится default автоматически;
- voice/STUN ветка отделяется от non-voice эксперимента.

## Ранний edge-IP профиль

Для наблюдаемых Cloudflare edge IP проверялась последовательность:

```text
--filter-tcp=443
--ipset-ip=<observed edges>
--out-range=-s1
--lua-desync=wssize:wsize=1:scale=6
--lua-desync=syndata:blob=fake_default_tls
```

Это была гипотеза для ранних пакетов, а не прямой порт WinDivert.

## Безопасность

Стратегия остаётся catalog data до явного выбора и owner-confirmed запуска. Проверки не запускают её и не меняют firewall/services.
