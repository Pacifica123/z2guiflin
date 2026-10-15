# Оркестратор стратегий (circular) — экспериментально

z2guiflin не перебирает стратегии сам. Для живого переключения используется
upstream-оркестратор `circular` из `core/zapret2/lua/zapret-auto.lua`
(описание — `core/zapret2/docs/manual.md`, раздел «circular»). GUI только
собирает для него корректные аргументы nfqws2 и показывает переключения из лога.

## Механизм

Профиль с оркестратором выглядит так (так его собирает
`zap2_gui.models.orchestrator.OrchestratedProfile`):

```
--filter-tcp=443 --filter-l7=tls ...
--out-range=-s34228
--in-range=-s5556
--lua-desync=circular:fails=3:time=60[:nld=N][:reqhost][:key=имя]
--in-range=x
--payload=tls_client_hello
--lua-desync=<стратегия 1>:strategy=1
--lua-desync=<стратегия 2, instance 1>:strategy=2[:final]
--lua-desync=<стратегия 2, instance 2>:strategy=2
```

* Каждая стратегия-кандидат — один или несколько `--lua-desync` instance.
  Теги `strategy=N` (1..N, без пропусков) назначаются автоматически; вручную
  `strategy`/`final` в кандидате указывать нельзя.
* `final` (опция «final на последней») останавливает ротацию на последней
  стратегии; без него после последней снова идёт первая.
* Состояние хранится по хосту в Lua-таблице `autostate.<key>.<host>`:
  `fails` — сколько неудач нужно для переключения (по умолчанию 3), `time` —
  через сколько секунд без неудач счётчик сбрасывается (60), `nld` — обрезать
  имя до N-уровневого домена, `reqhost` — не работать по IP без hostname,
  `key` — имя таблицы, чтобы разные профили не делили состояние.
* Нужен `--lua-init=@core/zapret2/lua/zapret-auto.lua`; конструктор пресетов
  добавляет его автоматически, если профиль использует `circular`.

Кандидаты берутся из `strategies/catalog.json` (каждый профиль strategy JSON,
у которого единственный `--payload`). Выбирайте кандидатов с одинаковым
payload. Собственные `--out-range` кандидатов заменяются окном `-s34228`.
Результаты Blockcheck в проекте не хранятся между сессиями, поэтому их можно
добавить только вручную.

## Нужен входящий захват

Детектор неудач (`standard_failure_detector`) смотрит на **входящие** пакеты:
RST от DPI, HTTP-redirect 302/307 на чужой домен, а также на исходящие
ретрансмиссии и «много UDP наружу, почти ничего внутрь». Поэтому:

* `--in-range=-s5556` включается только для экземпляра `circular` этого
  профиля и сразу выключается (`--in-range=x`) для кандидатов;
* firewall/NFQUEUE тоже должен отдавать начало входящего потока (SYN-ACK,
  FIN/RST). Если входящие пакеты не попадают в nfqws2, `circular` никогда не
  переключится — это не значит, что первая стратегия работает.

## Как читать лог

Запустите nfqws2 с debug-логом и найдите строки:

```
automate: host record key 'autostate.tls443.example.com'
standard_failure_detector: incoming RST s1 in range s4096
automate: failure detected
automate: failure counter 3/3
circular: rotate strategy to 2
circular: current strategy 2
```

`zap2_gui.models.orchestrator.parse_circular_log()` (и
`adapters.orchestrator_candidates.circular_switches_from_log()` для файла)
превращает такие строки в записи `{host, from, to, reason}`. Причины: `rst`,
`retransmission`, `http_redirect`, `udp_no_reply`, `unknown`.

## Ограничения

* Одно переключение ≠ устойчивая стратегия. Ротация означает только то, что
  предыдущая стратегия набрала `fails` неудач за окно `time`; новая может так
  же не работать, а ложные RST/ретрансмиссии бывают и без DPI.
* Состояние живёт в памяти nfqws2 и пропадает при перезапуске.
* Пример `strategies/orchestrated-circular-example.json` — эксперимент, не
  выбирается по умолчанию и не проверялся на реальной сети.
