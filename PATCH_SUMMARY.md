# 2026-10-21-strat-port-coverage — strat_collection: портируется 46 из 55 вместо 2

Третий патч пачки B. Автопорт winws1-стратегий из `presets/collections/strat_collection` в пресеты zapret2 отказывал почти всегда;
разбор показал, что большинство отказов — не принципиальные, а пробелы в сопоставлении.

## Что сделано (`adapters/strat_collection_port.py`, `adapters/strat_collection.py`)

- **hex-блобы** (`--dpi-desync-fake-http=0x0F0F0F0F`, `--dpi-desync-udplen-pattern=0xDEADBEEF` …) раньше искались как файлы.
  Теперь значение идёт прямо в `blob=`/`pattern=`, как принимает zapret2. `%BIN%` в путях снимается.
- **Устаревшие режимы nfqws1**: `split` → `fakedsplit`, `disorder` → `fakeddisorder`, `split2` → `multisplit`,
  `disorder2` → `multidisorder` (в nfqws1 это давно псевдонимы). Каждое такое преобразование пишется в «adaptations».
- **`--wssize=W:S`** → `--lua-desync=wssize:wsize=W:scale=S`. В таком профиле не добавляется выведенный `--filter-l7`:
  wssize срабатывает на SYN, когда L7 ещё не известен. Значение, записанное в .bat через пробел (`--wssize 1:6`), раньше терялось
  при разборе — теперь склеивается.
- **fake для неизвестного UDP** (`--dpi-desync-any-protocol` без блоба, голосовые порты Discord) — 64 нулевых байта:
  это значение `--dpi-desync-fake-unknown-udp` по умолчанию в nfqws1. Раньше порт отказывал «не угадываю»; теперь он делает то же,
  что делал nfqws1, и пишет это в «adaptations».
- По-прежнему не портируются: `--dup*` (5 стратегий) и `ipfrag2` (2) — однозначного аналога нет; 3 стратегии с fake на TCP-портах
  без известного протокола.

## Проверки

- `tests/test_strat_collection_port_coverage.py`: ≥45 портируемых, остаток только из известных причин, hex-блобы инлайн,
  wssize-профиль без `--filter-l7`, round-trip парсера для каждого портированного пресета.
- `tests/test_stage8j_r1_usertest_hot_swap_strat_ui.py`: ожидание «v1 отказывает» заменено на «v1 портируется с пометкой о 64 нулевых байтах».
- `bash meta_tools/run_tests.sh`, `check_board.py`, freeze пересчитан.

## Что осталось

- Проверить портированные стратегии на реальной сети (карточка в «Ждёт хоста»).
