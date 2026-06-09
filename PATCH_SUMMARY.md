# v0.4-alpha Stage 7: Discord desktop failure-driven target coverage

Патч переводит следующий шаг Discord-цикла из режима «нашли стратегию для `discord.com`» в режим честного per-target coverage.

## Почему это нужно

Первая owner verification показала, что Blockcheck нашёл несколько `AVAILABLE` стратегий для `discord.com`, но desktop Discord всё равно завис на `Checking for updates`. Значит, Stage 6 проверил слишком узкий слой: updater/download, gateway и CDN/media candidates должны проверяться отдельно.

## Что изменилось

- `discord-desktop` preset расширен `stable.dl2.discordapp.net`.
- `profiles/hostlists/default.hosts` теперь покрывает этот updater/download target.
- `BlockcheckOptions` получил `scan_mode`:
  - `stop-after-first-available`;
  - `scan-all-targets`;
  - `skip-dead-targets-only`.
- Для `discord-desktop` GUI/CLI default теперь ориентирован на `scan-all-targets`.
- Blockcheck Lab получил selector `Candidate mode` и кнопку `Coverage`.
- Single-candidate runs сохраняются в `.zap2/blockcheck/logs/candidates/`.
- Создаётся coverage manifest:

```text
.zap2/blockcheck/logs/candidates/coverage-manifest.json
```

- Новый CLI:

```bash
PYTHONPATH=gui python -m zap2_gui.app --blockcheck-coverage
```

- Export generated strategies теперь умеет брать AVAILABLE candidate logs из coverage manifest и добавляет `serviceTarget.coverage` в JSON стратегии.
- Strategy UX показывает coverage summary, чтобы `discord.com`-only успех не выглядел как полное подтверждение Discord desktop.
- Owner verification loop уточнён: при зависании на `Checking for updates` сначала смотреть `updates.discord.com` и `stable.dl2.discordapp.net`.

## Граница Stage 7

Патч не добавляет voice/UDP, не объединяет несколько стратегий автоматически, не запускает сетевые проверки без владельца и не меняет safety boundary Default workflow. Он даёт диагностическую инфраструктуру для следующего owner-прогона.

## Проверки

```bash
PYTHONPATH=gui python -m pytest \
  tests/test_blockcheck_target_coverage.py \
  tests/test_service_target_presets.py \
  tests/test_service_target_hostlist_alignment.py \
  tests/test_blockcheck_gui_lab.py \
  tests/test_service_aware_strategy_export.py \
  tests/test_discord_owner_verification_loop.py \
  tests/test_workspace_profiles_and_strategies.py \
  tests/test_v04_alpha_patch_roadmap.py \
  tests/test_documentation_language.py -q

python -m compileall -q gui tests
```
