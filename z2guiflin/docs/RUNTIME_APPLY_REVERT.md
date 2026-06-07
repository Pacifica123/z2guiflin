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

Правила направляют в workspace-specific NFQUEUE только те протоколы и порты, которые реально объявлены текущей strategy через `--filter-tcp`/`--filter-udp`. Для нынешней `manual-local` strategy это TCP 80/443; UDP/443 больше не ставится в очередь автоматически, пока в strategy нет соответствующего UDP-фильтра и UDP-desync. Номер очереди детерминированно выбирается для пары workspace/profile и одинаково используется в nftables apply plan и session args `nfqws2`. Это снижает риск конфликта со stale/manual процессом из предыдущего workspace и не ломает QUIC без явной UDP-стратегии.

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
