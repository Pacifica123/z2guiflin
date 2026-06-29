# Launch composer readiness prechecks

Дата: 2026-06-29

## Зачем

Комбинированный запуск должен вести себя как запуск выбранного набора, а не как best-effort запуск отдельных частей.

Если выбраны `zapret-default + tunnel-vless`, но `nfqws2` не собран, старый flow всё равно запускал VLESS tunnel и заканчивал с `Z2-LAUNCH-PARTIAL`. Это технически верно, но плохо для UX: причина была видна только в длинном output.

## Новое правило

Перед запуском composer проверяет readiness выбранных supported-компонентов.

Если выбранный stopped-компонент не ready, composer возвращает:

```text
Launch composer start: blocked
reason: selected components are not ready
blockers:
- zapret-default: needs nfqws2 build
```

При таком блокере не запускается ни Zapret, ни VLESS. Это защищает от частичного состояния.

## Новый код ошибки

`Z2-ZAPRET-BINARY-MISSING` означает:

```text
Zapret не запущен: nfqws2 не собран или не executable.
```

Пользовательский следующий шаг: выполнить build workflow из GUI, затем повторить комбинированный запуск.
