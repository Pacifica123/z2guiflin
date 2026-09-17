# Blockcheck Lab в GUI — v0.3-dev Stage 1

Этот слой переносит часть upstream `blockcheck2.sh` в GUI как ручной diagnostic
lab для владельца. Цель stage — не автоматически «починить YouTube», а дать
понятный способ подобрать рабочую строку `nfqws2` для конкретного домена и
потом уже осознанно превратить её в project strategy.

## Что добавлено

- Вкладка `Диагностика` теперь открывает `Blockcheck lab`, а не placeholder.
- Дефолтные targets: `youtube.com www.youtube.com`.
- Дефолтные protocol checks: HTTPS TLS1.2, HTTPS TLS1.3 и HTTP/3 QUIC.
- HTTP выключен по умолчанию, потому что для YouTube он обычно не главный сигнал.
- DNS precheck включён по умолчанию: Blockcheck всё равно обязан разрешить target через `mdig`, поэтому ранняя DNS-диагностика предотвращает неясный `curl code 6`; отключать её следует только для осознанной диагностики. Раньше precheck был выключен, что маскировало resolver failures.
  отдельной DNS-диагностикой.
- Результат сохраняется в `.zap2/blockcheck/logs/last-blockcheck.txt`.
- Adapter пытается вытащить из stdout краткие строки `SUMMARY` и `working
  strategy found`, чтобы их было легче перенести в будущий strategy editor.

## Команды CLI

```bash
PYTHONPATH=gui python -m zap2_gui.app --blockcheck-preflight
PYTHONPATH=gui python -m zap2_gui.app --blockcheck-plan --blockcheck-domains "youtube.com www.youtube.com"
PYTHONPATH=gui python -m zap2_gui.app --blockcheck-run --blockcheck-domains "youtube.com www.youtube.com"
PYTHONPATH=gui python -m zap2_gui.app --blockcheck-last-log
```

`--blockcheck-plan` безопасен: он только печатает preflight и команду запуска.
`--blockcheck-run` исполняет upstream script через `sudo -A` и графический
`SUDO_ASKPASS` helper.

## Граница привилегий

GUI не хранит пароль и не просит его в терминале. Для run используется тот же
локальный askpass helper, что и для default start/stop:

```text
sudo -A env ... /bin/sh core/zapret2/blockcheck2.sh
```

Blockcheck не вызывает `install_easy.sh`, `install_bin.sh` или другие upstream
installer scripts. Но сам upstream blockcheck — это privileged diagnostic tool:
он временно меняет firewall redirection, запускает probe-процесс и затем очищает
состояние через собственный cleanup. Поэтому перед запуском нужно выключить
Default workflow, VPN и другие DPI-bypass процессы.

## Предварительная проверка

Preflight ничего не исполняет и проверяет только наличие:

- `core/zapret2/blockcheck2.sh`;
- исполняемого `core/zapret2/nfq2/nfqws2`;
- исполняемого `core/zapret2/mdig/mdig`;
- `curl`;
- `sudo`;
- `nft` или `iptables`.

Если `nfqws2` или `mdig` отсутствуют, owner action — локально собрать core target
`all` или соответствующий unit. GUI не запускает `make` скрыто из blockcheck lab.

## Почему это Stage 1

После перехода на `v0.3-dev` нумерация dev-цикла сбрасывается. Предыдущие
Stage 16/17 остаются историческими переходными hotfix-патчами вокруг safer
interception и saved owner-rules execution. Этот документ считается первым
нормальным stage нового dev-loop.

## v0.3-dev Stage 2: локальная сборка prerequisites

Первый реальный запуск показал важный разрыв: `blockcheck2.sh` стартовал через
sudo, но падал на upstream preflight, потому что в workspace не было исполняемых
`core/zapret2/nfq2/nfqws2` и `core/zapret2/mdig/mdig`. Stage 2 закрывает этот
разрыв до запроса sudo.

Теперь `Blockcheck lab` умеет:

- показать отдельный план сборки prerequisites: `make all` внутри
  `core/zapret2`;
- запустить эту сборку явной кнопкой владельца без sudo;
- не вызывать `install_bin.sh`, `install_easy.sh`, `install_prereq.sh` или другие
  upstream installer scripts;
- перед privileged blockcheck run ещё раз проверить preflight и остановиться до
  `sudo -A`, если `nfqws2`, `mdig`, `curl`, `sudo` или firewall toolchain не
  готовы.

Новые CLI-эквиваленты:

```bash
PYTHONPATH=gui python -m zap2_gui.app --blockcheck-build-plan
PYTHONPATH=gui python -m zap2_gui.app --blockcheck-build
```

`--blockcheck-build-plan` только печатает план. `--blockcheck-build` запускает
локальный `make all` без sudo и без изменений firewall/services. Если системные
заголовки или build tools отсутствуют, команда блокируется на dependency
preflight и печатает подсказки пакетов для Debian/Ubuntu, Fedora/RHEL-like,
Arch/Manjaro и openSUSE.

`--blockcheck-run` теперь не должен доходить до upstream ошибки вида
`nfqws2 or mdig is not available`: GUI/CLI wrapper заранее пишет понятное
сообщение, сохраняет last log и не показывает парольный prompt, пока prerequisites
не готовы.


## v0.3-dev Stage 3: live run без заморозки GUI

Практический запуск показал две связанные проблемы: `blockcheck2.sh` может
работать долго, а синхронный `subprocess.run()` в GUI-потоке замораживал всё
окно до завершения процесса. Stage 3 переводит именно GUI-run на `QProcess`:
процесс идёт в фоне, stdout/stderr дописываются в поле лога по мере появления,
а окно остаётся отзывчивым.

Общий таймер больше не используется как основной механизм контроля. Это важно,
потому что долгий scan сам по себе не означает ошибку: иногда blockcheck должен
перебрать много candidate strategies. Вместо произвольного лимита добавлена
явная owner-кнопка `Остановить`. Она сначала отправляет `SIGINT`, чтобы
upstream `blockcheck2.sh` выполнил собственный cleanup. Только если процесс не
завершился за 10 секунд, GUI переходит к аварийному `terminate()`, а затем к
`kill()`. Прямой `SIGTERM` нельзя считать штатной остановкой: upstream script
гарантированно связывает cleanup с обработчиком `SIGINT`.

Последний лог теперь обновляется и во время выполнения, а не только после
завершения. Поэтому кнопку `Последний лог` можно использовать после остановки
или падения GUI без потери уже полученного вывода.

Загруженный ранее CLI wrapper для стратегий использовал не общий таймер, а
событийную модель: читать stdout построчно, считать протестированные и найденные
стратегии, останавливать дочернюю process group только по осмысленным условиям
вроде достаточного числа `AVAILABLE` или долгой серии без результата. В Stage 3
мы переносим безопасную часть этой идеи — потоковое чтение и явную остановку
владельцем. Автоматические эвристики ранней остановки пока намеренно не
включены в GUI по умолчанию: их нужно валидировать отдельно, чтобы не срезать
длинный, но потенциально полезный поиск.

## v0.3-dev Stage 4: owner UID/GID для Lua после privilege drop

Live-run выявил новую проблему: `blockcheck2.sh` стартует scan, но `nfqws2`
пишет в stderr:

```text
LUA file '.../core/zapret2/lua/zapret-lib.lua' or '...zapret-lib.lua.gz' not accessible
I drop my privileges and do not run Lua as root
check file permissions and +x rights on all directories in the path
```

Сами Lua-файлы находятся в vendored core tree. Ошибка возникает не из-за их
отсутствия, а из-за того, что upstream blockcheck передаёт `nfqws2` дефолтный
`--uid 1:3003`, если `WS_UID/WS_GID` не заданы. После сброса root такой user не
обязан иметь право прохода по `/home/<owner>/projects/...`, поэтому Lua-init не
может прочитать файлы в workspace.

Stage 4 меняет только GUI/CLI wrapper вокруг blockcheck:

- при построении команды добавляются `WS_UID` и `WS_GID` владельца GUI-процесса;
- если wrapper уже запущен через sudo, используются `SUDO_UID/SUDO_GID`;
- `Blockcheck plan` печатает выбранный worker uid/gid и source выбора;
- preflight проверяет наличие `lua/zapret-lib.lua` и `lua/zapret-antidpi.lua`;
- Stop больше не показывает `QProcess error: Crashed`, если crash был ожидаемым
  результатом owner-остановки.

Это не добавляет installer scripts, не меняет persistent services и не ослабляет
границу sudo: root всё ещё нужен только для upstream firewall/NFQUEUE действий,
а `nfqws2` после старта сбрасывается к владельцу workspace вместо synthetic
`1:3003`.

## v0.3-dev Stage 5: краткая статистика после Stop/finish

Практический запуск показал, что live streaming решает проблему заморозки окна,
но длинный blockcheck всё равно трудно интерпретировать: после ручного Stop в
логе остаются сотни строк вида `curl: (28) ...` и `UNAVAILABLE code=28`, а
понять общий масштаб прогона приходится вручную.

Stage 5 добавляет консервативный parser поверх уже полученного вывода. Он не
останавливает blockcheck автоматически и не сокращает поиск стратегий. Его задача
только summarization после завершения или остановки владельцем:

- `strategy checks seen` — количество строк `- curl_test... : nfqws2 ...`;
- `available strategies` — количество стратегий, для которых внутри активной
  пробы появился `!!!!! AVAILABLE !!!!!` или `working strategy found`;
- `unavailable strategies` — количество проб, дошедших до `UNAVAILABLE`;
- `in-progress/unknown checks` — последняя или оборванная проба без финального
  результата на момент Stop;
- `port precheck` — сколько IP перед scan отвечали/не отвечали на TCP connect;
- `top unavailable reasons` — нормализованные частые причины, например
  `curl code 28: connection timed out`;
- `scripts seen` и `top probes` — какие upstream blockcheck sections уже были
  пройдены.

Секция пишется и в GUI footer, и в `.zap2/blockcheck/logs/last-blockcheck.txt`:

```text
===== BLOCKCHECK RUN STATISTICS =====
Blockcheck run statistics
strategy checks seen: 123
available strategies: 0
unavailable strategies: 122
in-progress/unknown checks: 1
port precheck: connects=0; failed=4
top unavailable reasons:
  - curl code 28: connection timed out: 122
```

Parser намеренно игнорирует `!!!!! AVAILABLE !!!!!` из ручных IP block tests,
если в этот момент не активна строка strategy attempt. Это важно, потому что
upstream blockcheck может печатать `AVAILABLE` для контрольного `iana.org`, и это
не означает найденную рабочую стратегию для YouTube.

## v0.3-dev Stage 6: экспорт AVAILABLE в generated strategies

Stage 6 замыкает ручную цепочку `Blockcheck lab -> generated strategy -> выбор -> Default workflow`.
После длинного run и статистики владелец теперь может нажать `Создать стратегии`:
GUI прочитает `.zap2/blockcheck/logs/last-blockcheck.txt`, найдёт только реальные
`AVAILABLE` строки вида `- curl_test... : nfqws2 ...`, создаст по одному
strategy JSON на каждую найденную команду и добавит эти файлы в
`strategies/catalog.json`.

Файлы кладутся в:

```text
strategies/generated/
```

Идентификатор строится по схеме:

```text
blockcheck-<target>-<mtime-last-log>-NN
```

Каждый generated strategy получает безопасные базовые runtime args:

- Lua init: `zapret-lib.lua` и `zapret-antidpi.lua`;
- protocol filter по типу probe: TCP/443 для HTTPS/TLS, UDP/443 для HTTP/3/QUIC,
  TCP/80 для HTTP;
- оригинальную `nfqws2 ...` часть из blockcheck без объединения с другими
  стратегиями.

Стратегии намеренно создаются раздельно. Слепить 38 `AVAILABLE` строк в один
`runtimeArgs` было бы методологически неверно: blockcheck проверял их как
отдельные варианты, а не как одну составную команду.

CLI-эквивалент:

```bash
PYTHONPATH=gui python -m zap2_gui.app --blockcheck-export-strategies
```

Команда не требует sudo, не меняет firewall/services и не запускает `nfqws2`.
Она меняет только рабочее дерево проекта: `strategies/generated/*.json` и
`strategies/catalog.json`.

## v0.3-dev Stage 7: sequential candidates и safe export source

Stage 7 исправляет важный сценарий после появления статистики: `DOMAINS=youtube.com www.youtube.com` больше не рассматривается GUI как один монолитный запуск. Blockcheck lab запускает targets последовательно. Для каждого target создаётся отдельный `BlockcheckOptions` с одним доменом, отдельный live process и отдельная статистика.

Новая защита не является произвольным timeout. GUI читает live stdout и отслеживает upstream-блок вида:

```text
* port block tests ipv4 youtube.com:443
142.251.127.136 does not connect. netcat code 1
...
* curl_test_https_tls12 ipv4 youtube.com
```

Если после port precheck для текущего target было `connects=0` и `failed>0`, GUI завершает только этот candidate и пишет в footer:

```text
auto skipped dead target: yes
auto skip reason: port-precheck-dead-target ...
```

Затем, если в списке есть следующий target, GUI переходит к нему. Если target не провалил port precheck, scan остаётся долгим и управляется владельцем через Stop, без общего таймера.

Статистика теперь выводит `verdict`. Для dead-target случая verdict выглядит так:

```text
verdict: port-precheck-dead-target: strategy scan skipped/should be skipped
```

Также Stage 7 разделяет «последний запуск» и «последний успешный источник для экспорта». `last-blockcheck.txt` остаётся live/diagnostic логом. `latest-successful-blockcheck.txt` обновляется только когда parser увидел хотя бы одну настоящую `AVAILABLE` nfqws2 strategy attempt. Кнопка «Создать стратегии» сначала читает successful log, поэтому неудачный последний run не уничтожает возможность экспортировать предыдущие найденные стратегии.

## v0.3-stable итог и роль в v0.4-alpha

После Stage 7 владелец подтвердил `v0.3-stable`: текущая Blockcheck/Strategies/Default цепочка уже умеет найти стратегии для базовых доменных имён, экспортировать их, выбрать одну и запустить `nfqws2` так, что это работает как минимум для YouTube. Это важная граница: Blockcheck lab больше не только диагностика, а практический вход в runtime workflow.

В `v0.4-alpha` тот же lab становится основным инструментом исследования desktop Discord. Ближайшие изменения должны быть service-aware, но без преждевременной магии:

- добавить удобные candidate targets для Discord desktop;
- не считать один неудачный target провалом всего сервиса;
- сохранять successful source отдельно для Discord так же аккуратно, как сейчас для YouTube;
- экспортировать generated strategies с понятным target/service именем;
- позволить владельцу выбрать Discord-стратегию и запустить её через существующий Default workflow.

Ограничение `v0.4-*`: Blockcheck lab не обязан автоматически объединять YouTube и Discord в одну strategy. На этом цикле достаточно корректного выбора одной целевой стратегии за раз.


## v0.4-alpha Stage 7d — Discord port-precheck и Blockcheck Lab UX

Stage 7d фиксирует два наблюдения owner-run после Stage 7c.

Первое: `stable.dl2.discordapp.net` уже давал десятки `AVAILABLE` стратегий, но следующий запуск мог пометить его `dead-target` на основании одного неудачного `nc` в port precheck. Для Discord ordered phases это слишком агрессивно: CDN/updater адреса могут быть плавающими, а `nc`-проверка не должна блокировать сам подбор стратегии. Поэтому Blockcheck Lab получил режим `dead-target guard`: для простых проверок он остаётся `auto-stop`, а для `discord-desktop` по умолчанию выставляется `observe-only`. В `observe-only` портовый precheck остаётся в логе и статистике, но GUI не убивает candidate до strategy scan.

Второе: экран Blockcheck Lab стал слишком плотным после добавления service policy/tournament controls. Stage 7d расширяет дефолтное окно, делит действия на две строки, укорачивает подписи кнопок и добавляет явный переключатель `Auto-skip dead target`, чтобы владелец видел, когда включён риск раннего пропуска candidate.

Граница Stage 7d: патч не портирует Flowseal/Windows presets в исполняемый Linux runtime автоматически. Он фиксирует источник ложного `dead-target`, улучшает управляемость GUI и документирует, какие идеи Flowseal/Windows стоит переносить осторожно.

## v0.4-alpha Stage 7e — human tournament log and less cramped controls

Stage 7e separates two streams in Blockcheck Lab for desktop-style ordered presets. During a phase-gated Discord run, the text area now shows a GUI-level tournament log instead of continuously dumping the full upstream `blockcheck2.sh` output. Raw stdout/stderr are still collected and written to `last-blockcheck.txt` and per-candidate logs, and the `Raw log` button remains available for detailed inspection.

The human log is intentionally closer to the owner mental model:

```text
[GUI tournament] Фаза 1/5 updater: проверяем alternative 1/2 — stable.dl2.discordapp.net
[GUI tournament] Найдена AVAILABLE стратегия для фазы 1 ...
[GUI tournament] стратегия-рекордсмен: nfqws2 ...
[GUI tournament] Фаза пройдена; переходим к следующей обязательной фазе ...
[GUI tournament] Стратегия/alternative не прошла фазу 2 ...
[GUI tournament] Блокчек остановлен вручную / завершил работу ...
топ стратегий: ...
```

This does not delete upstream evidence. It only keeps the main GUI screen readable while the raw log remains in `.zap2/blockcheck/logs/` for debugging and export.

Stage 7e also raises minimum heights for combo boxes, spin boxes and action buttons, sets safer form column widths, keeps actions in two rows, and renames `Last log` to `Raw log` so the owner understands that the button is the escape hatch to the unfiltered upstream transcript.

## v0.4-alpha Stage 7f: bounded tournament progress and less cramped UI

Stage 7f fixes the owner-observed case where an ordered Discord phase run stayed on `stable.dl2.discordapp.net` until manual Stop. For `ordered-target-chain` presets the GUI now exposes an `Alt check cap`: once a phase alternative has produced that many strategy checks without any `AVAILABLE`, the GUI terminates only that upstream candidate and moves to the next OR alternative in the same phase. If an `AVAILABLE` appears first, the existing early-stop path still advances to the next required phase immediately.

The default cap for `discord-desktop` is 160 checks. Owners can set it to `off` when they want a full upstream search on one target, or raise it when a target is known to produce late successes.

The Blockcheck Lab layout was also widened and de-stretched: key controls now have maximum widths, the preset hint has a reserved two-line area, and the main window default size is roomier. This does not change runtime behavior; it only makes the diagnostics page more readable while the tournament log is being watched.

## Stage 7g: Discord endpoint discovery button

The Blockcheck Lab action row now includes `Endpoints`. It prints a read-only plan and the latest saved Discord endpoint discovery snapshot. The actual long-running watch remains CLI-first:

```bash
PYTHONPATH=gui python -m zap2_gui.app --discord-endpoint-watch --discord-endpoint-seconds 90
```

The watch samples `ss -tunp` and `pgrep -af [Dd]iscord`; it does not run sudo, mutate firewall rules or capture payloads. It is intended for the `Checking for updates` dead end, where guessed targets can be wrong.

## Stage 7h: updater socket state discovery

Stage 7h extends the Stage 7g endpoint discovery loop with TCP state/timer evidence and best-effort DNS mapping. The owner observed the Discord updater splash opening a TCP/443 socket in `SYN-SENT` toward a Cloudflare edge IP that resolves in the current environment for `updates.discord.com`. This means the failure is visible before a completed TLS/HTTP request on that socket, so more curl/TLS strategy tournaments against later Discord phases are not the next best diagnostic step.

New CLI helpers:

```bash
PYTHONPATH=gui python -m zap2_gui.app --discord-endpoint-watch --discord-endpoint-seconds 30
PYTHONPATH=gui python -m zap2_gui.app --discord-endpoint-report
PYTHONPATH=gui python -m zap2_gui.app --discord-netlog-plan
```

The watcher remains read-only: it samples `ss`, `pgrep` and DNS metadata, does not use sudo, does not mutate firewall/services and does not capture packet payloads. The optional netlog plan is not executed automatically because Chromium netlogs can contain privacy-sensitive URLs, headers or token-like values.

### v0.4-alpha Stage 7i — Discord DNS edge diagnosis

Stage 7i переносит идею Windows GUI DNS-проверок в read-only Linux diagnostic. Команды `--discord-dns-edge-plan` и `--discord-dns-edge-check` сравнивают system/Cloudflare/Google/Quad9/AdGuard/OpenDNS resolvers и проверяют TCP/443 для возвращённых Discord edge IP. Это не меняет DNS и не требует sudo. Если найден `connect-ok` edge, DNS/hosts steering можно рассматривать как owner-confirmed эксперимент. Если все edge IP timeout, то текущий Discord updater blocker шире, чем DNS-подмена, и обычные TLS Blockcheck-стратегии всё ещё не упражняются на SYN-SENT socket.


## v0.4-alpha: безопасная остановка Blockcheck

Compact Blockcheck в конструкторе и Blockcheck Lab больше не обрывают upstream
run через `QProcess.terminate()` сразу после `AVAILABLE`. Такой SIGTERM мог
завершить shell до `unprepare_all()` и оставить временную таблицу
`inet blockcheck<PID>` или probe-процесс `nfqws2`. Обычная остановка теперь
посылает SIGINT и ждёт cleanup.

В конструкторе первая найденная `AVAILABLE` строка сохраняется, но текущий target
дорабатывает штатно. После его завершения targets дальше не перебираются. Это
медленнее немедленного kill, зато не оставляет firewall в промежуточном состоянии.

Один `AVAILABLE` остаётся доказательством только для одного target/probe. Он не
является готовым составным preset для всего сервиса.


## Target-specific DNS guard

GUI/CLI wrapper выполняет read-only `mdig` probe для каждого выбранного service target в том же sudo/QProcess-контексте, который затем запускает upstream `blockcheck2.sh`. Если выбранный target не получает адрес для requested `IPVS`, wrapper завершает run до upstream firewall preparation с кодом 6 и прямым сообщением `target DNS preflight FAILED`. Общая DNS/hijack диагностика остаётся внутри upstream Blockcheck; `SKIP_DNSCHECK` по умолчанию выключен.


## Target-specific DNS gate

Перед privileged upstream scan локальный `tools/blockcheck_target_preflight.sh` проверяет выбранные service targets через тот же vendored `mdig` и требуемые `IPVS`. Если конкретный target не возвращает адрес, run завершается кодом 6 **до** запуска `blockcheck2.sh` и до временных firewall changes. Upstream `DNS precheck` остаётся включённым по умолчанию и отвечает за общую DNS/hijack диагностику; wrapper не дублирует её, а закрывает отдельный случай, когда общая DNS-проверка проходит, но выбранный `youtube.com`/Discord endpoint не резолвится.
