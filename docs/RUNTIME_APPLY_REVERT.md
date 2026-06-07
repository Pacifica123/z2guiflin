# Runtime apply/revert — Stage 12

Stage 12 вводит первый owner-confirmed путь для системных правил runtime lifecycle. Он отделён от bootstrap, local build и session runner.

## Что добавлено

Новый adapter:

```text
/gui/zap2_gui/adapters/runtime_apply.py
```

Он умеет строить и сохранять два типа планов:

```bash
PYTHONPATH=gui python -m zap2_gui.app --runtime-apply-plan --profile default
PYTHONPATH=gui python -m zap2_gui.app --runtime-revert-plan --profile default
```

Планы сохраняются в `.zap2/runtime/plans/`, получают `planHash`, rollback notes и требуют owner confirmation через уже существующий gate:

```bash
PYTHONPATH=gui python -m zap2_gui.app --runtime-confirm runtime-default-manual-local-apply-owner-rules-plan
PYTHONPATH=gui python -m zap2_gui.app --runtime-confirm runtime-default-manual-local-revert-owner-rules-plan
```

После подтверждения владелец может локально исполнить plan:

```bash
sudo PYTHONPATH=gui python -m zap2_gui.app --runtime-apply --profile default --confirm runtime-default-manual-local-apply-owner-rules-plan
sudo PYTHONPATH=gui python -m zap2_gui.app --runtime-revert --profile default --confirm runtime-default-manual-local-revert-owner-rules-plan
```

## Что именно делает apply

Stage 12 использует `nftables` как первый backend. Default profile создаёт отдельную owned table:

```text
inet zap2_default
```

Внутри неё создаётся отдельная chain для локального исходящего трафика:

```text
local_out
```

Правила направляют локальный TCP 80/443 и UDP 443 в workspace-specific NFQUEUE с `queue bypass`. Номер очереди больше не фиксируется глобально на `200`: он детерминированно выбирается для пары workspace/profile и одинаково используется в nftables apply plan и session args `nfqws2`. Это снижает риск конфликта со stale/manual процессом из предыдущего workspace.

Stage 12 не пытается покрыть все возможные router/LAN/WAN схемы upstream zapret2. Это минимальный single-user desktop-oriented backend для default strategy. Расширенные схемы interception должны появляться отдельными strategy/profile options после того, как базовый lifecycle станет устойчивым.

## Что делает revert

Revert удаляет только owned table:

```text
nft delete table inet zap2_default
```

Он не очищает чужие tables/chains/rules и не делает глобальный firewall reset. Если owned table уже отсутствует, guarded executor считает это безопасным состоянием для повторного stop workflow.

## Safety boundary

Stage 12 запрещает:

- `curl`/`wget` remote bootstrap;
- upstream `install_easy.sh`/`uninstall_easy.sh`;
- `systemctl` и service mode;
- скрытое исполнение в devctl-проверках;
- применение правил без сохранённого plan, совпадающего `planHash` и owner confirmation.

Автоматические проверки используют fake runner и не вызывают настоящий `nft`, не требуют root и не меняют firewall.

## Почему это не bootstrap

Bootstrap отвечает за структуру проекта, vendored-core и developer tooling. Runtime apply/revert отвечает только за временные системные правила, необходимые для работы текущей runtime session. Эти уровни нельзя смешивать: установка/обновление проекта не должна автоматически менять firewall, а runtime stop/revert не должен удалять или пересобирать проект.

## Использование в default workflow

В Stage 14 apply/revert слой используется как child plan внутри composite default workflow. Пользователь подтверждает composite plan, после чего workflow создаёт derived confirmations для child plans только если их сохранённые hashes совпадают с composite plan. Это позволяет запускать `default-start/default-stop` одной понятной парой команд, не теряя hash-gate из Stage 10–12.

## v0.3-dev Stage 16 — safer local interception

Stage 16 меняет смысл default apply с «перехватить все локальные 80/443/UDP443»
на более узкий single-owner scope:

- порты берутся из активной strategy: `--filter-tcp` и `--filter-udp`;
- если strategy не содержит `--filter-udp`, UDP/443 не добавляется неявно;
- nftables rule получает `meta skuid <owner_uid>`, поэтому root/NetworkManager
  connectivity checks не должны уходить в NFQUEUE вместе с браузером владельца;
- rule получает loop guard `meta mark & 0x40000000 == 0`, а session args явно
  передают `--fwmark=0x40000000`, чтобы сгенерированные nfqws2 пакеты не
  переочередивались повторно;
- перехват ограничен ранними исходящими пакетами connection через `ct original
  packets`, а не всем TCP/UDP потоком.

Это не финальная оптимальная zapret2-схема, а безопасный следующий шаг для GUI
runtime: если соединение ломается, stop/revert по-прежнему удаляет только owned
`inet zap2_default`, а диагностика показывает конкретный UID, mark и список
портов, которые были поставлены в очередь.


## v0.3-dev Stage 17 — saved-plan execution under sudo

Stage 17 исправляет регрессию GUI start, где privileged `sudo -A` execution
мог заново собрать owner-rules plan с другой runtime identity и получить ошибку:

```text
Prepared owner-rules plan устарел: текущий planHash не совпадает с сохранённым
```

Executor теперь валидирует hash сохранённого owner-confirmed plan и confirmation,
а затем исполняет именно сохранённые команды из этого plan. Это сохраняет
согласованный `ownerUid`, `nfqueueNum`, strategy-derived port set и nft syntax
между шагами `plan -> confirm -> sudo execute`. Дополнительно loop guard syntax
исправлен на nftables-совместимое выражение `meta mark & 0x40000000 == 0`.
