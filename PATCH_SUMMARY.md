# v0.4-alpha Stage 7a: service coverage policy/tournament groundwork

Патч добавляет универсальный слой `service coverage policy`, чтобы пользователь, GUI и Blockcheck adapter одинаково понимали, какой тип покрытия нужен конкретному service target preset.

## Зачем это нужно

После Stage 7 стало видно, что простой per-target scan полезен, но недостаточен как модель для desktop-приложений. YouTube baseline может жить в режиме «любой рабочий домен уже полезен», а Discord desktop требует ordered chain: сначала updater/download, затем app/API, gateway и CDN/media.

## Что изменилось

- В `gui/zap2_gui/models/service_targets.py` добавлен `ServiceCoveragePolicy`.
- Registry теперь различает режимы:
  - `any-target-available`;
  - `maximize-targets`;
  - `ordered-target-chain`;
  - `custom-manual`.
- `youtube-basic` получил policy `any-target-available` и recommended scan mode `stop-after-first-available`.
- `discord-desktop` получил policy `ordered-target-chain` и recommended scan mode `scan-all-targets`.
- Discord target order теперь updater-first:

```text
updates.discord.com
stable.dl2.discordapp.net
discord.com
gateway.discord.gg
cdn.discordapp.com
media.discordapp.net
discord.media
discordapp.net
discord.gg
```

- `BlockcheckOptions` теперь умеет отдавать `ordered_domains_for_policy()`.
- Blockcheck plan/log/env теперь фиксируют:

```text
ZAP2_SERVICE_COVERAGE_POLICY
ZAP2_SERVICE_COVERAGE_ORDER_MODE
```

- Coverage manifest сохраняет `coveragePolicy`, `coverageOrderMode`, `recommendedScanMode` и `stopRule`.
- Strategy export добавляет `serviceTarget.coveragePolicy` в generated strategy JSON.
- GUI Blockcheck Lab получил read-only buttons:
  - `Policy`;
  - `Tournament`.
- CLI получил read-only команды:

```bash
PYTHONPATH=gui python -m zap2_gui.app --blockcheck-service-policy --blockcheck-target-preset discord-desktop
PYTHONPATH=gui python -m zap2_gui.app --blockcheck-tournament --blockcheck-target-preset discord-desktop
```

- Новый документ:

```text
docs/SERVICE_COVERAGE_POLICIES.md
```

- Новый тестовый contract:

```text
tests/test_service_coverage_policy_tournament.py
```

## Граница Stage 7a

Патч не добавляет voice/UDP, не запускает сетевые проверки без владельца, не меняет Default workflow safety boundary и не утверждает, что upstream `blockcheck2.sh` уже умеет доказать одну найденную `nfqws2`-команду на всех target-ах автоматически.

Stage 7a создаёт общий policy/tournament контракт и меняет практический порядок Discord-проверки на updater-first, чтобы следующий owner-run быстрее отвечал на вопрос про зависание `Checking for updates`.

## Проверки

```bash
PYTHONPATH=gui python -m pytest \
  tests/test_service_coverage_policy_tournament.py \
  tests/test_service_target_presets.py \
  tests/test_service_target_hostlist_alignment.py \
  tests/test_blockcheck_target_coverage.py \
  tests/test_blockcheck_gui_lab.py \
  tests/test_service_aware_strategy_export.py \
  tests/test_discord_owner_verification_loop.py \
  tests/test_workspace_profiles_and_strategies.py \
  tests/test_v04_alpha_patch_roadmap.py \
  tests/test_documentation_language.py -q

python -m compileall -q gui tests
```
