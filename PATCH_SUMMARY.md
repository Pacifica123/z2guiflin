# v0.4-alpha Stage 7b: phase-aware one-strategy tournament

Патч исправляет модель Stage 7a по схеме владельца: стратегии должны проверяться по одной, а не пачкой `N` стратегий на одном target-е. Одна стратегия-кандидат идёт через цепочку фаз и либо становится новым record-holder, либо помечается непрошедшей.

## Что изменилось

- Добавлена фазовая модель service coverage:
  - фазы связаны через `AND`;
  - targets внутри одной фазы связаны через `OR`.
- `discord-desktop` теперь описан как фазы:
  1. `updater`: `stable.dl2.discordapp.net` OR `updates.discord.com`;
  2. `app-api`: `discord.com`;
  3. `gateway`: `gateway.discord.gg`;
  4. `cdn-media`: `cdn.discordapp.com` OR `media.discordapp.net` OR `discord.media` OR `discordapp.net`;
  5. `invite`: `discord.gg`.
- `Tournament` view теперь показывает не только target coverage, но и phase score / phase prefix / first blocker phase.
- `updates.discord.com` больше не обнуляет ordered prefix, если updater-фаза прошла через `stable.dl2.discordapp.net`.
- Добавлен one-strategy validation bridge через upstream `custom` lists:
  - из generated strategy берётся одна `nfqws2`-команда;
  - runtime scaffolding (`--lua-init`, `--filter-*`) отбрасывается;
  - команда пишется в `.zap2/blockcheck/tournament/custom-lists/<strategy>/list_https_tls12.txt` и `list_https_tls13.txt`.
- Добавлен CLI plan:

```bash
PYTHONPATH=gui python -m zap2_gui.app --blockcheck-validate-strategy-plan <strategy-id> --blockcheck-domains discord.com
```

## Граница

Stage 7b не запускает автоматический полный tournament сам по себе. Он вводит общий фазовый контракт и мост one-strategy custom-list validation, чтобы следующий слой мог без переписывания GUI/ядра реализовать AFK-режим: взять стратегию, проверить фазу, продвинуть record-holder, перейти к следующей фазе или кандидату.

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
