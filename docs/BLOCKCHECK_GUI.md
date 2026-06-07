# GUI Blockcheck lab — v0.3-dev Stage 1

Этот слой переносит часть upstream `blockcheck2.sh` в GUI как ручной diagnostic
lab для владельца. Цель stage — не автоматически «починить YouTube», а дать
понятный способ подобрать рабочую строку `nfqws2` для конкретного домена и
потом уже осознанно превратить её в project strategy.

## Что добавлено

- Вкладка `Диагностика` теперь открывает `Blockcheck lab`, а не placeholder.
- Дефолтные targets: `youtube.com www.youtube.com`.
- Дефолтные protocol checks: HTTPS TLS1.2, HTTPS TLS1.3 и HTTP/3 QUIC.
- HTTP выключен по умолчанию, потому что для YouTube он обычно не главный сигнал.
- DNS precheck выключен по умолчанию, чтобы не смешивать подбор DPI-strategy с
  отдельной DNS-диагностикой.
- Результат сохраняется в `.zap2/blockcheck/logs/last-blockcheck.txt`.
- Adapter пытается вытащить из stdout краткие строки `SUMMARY` и `working
  strategy found`, чтобы их было легче перенести в будущий strategy editor.

## CLI

```bash
PYTHONPATH=gui python -m zap2_gui.app --blockcheck-preflight
PYTHONPATH=gui python -m zap2_gui.app --blockcheck-plan --blockcheck-domains "youtube.com www.youtube.com"
PYTHONPATH=gui python -m zap2_gui.app --blockcheck-run --blockcheck-domains "youtube.com www.youtube.com"
PYTHONPATH=gui python -m zap2_gui.app --blockcheck-last-log
```

`--blockcheck-plan` безопасен: он только печатает preflight и команду запуска.
`--blockcheck-run` исполняет upstream script через `sudo -A` и графический
`SUDO_ASKPASS` helper.

## Privilege boundary

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

## Preflight

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
явная owner-кнопка `Остановить`, которая сначала отправляет `terminate()`, а
потом при необходимости добивает процесс через `kill()`.

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
