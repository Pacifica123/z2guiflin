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
