# v0.4-alpha Stage 6: Discord non-voice owner verification loop

Патч добавляет последний подготовительный слой перед личной проверкой владельца:
read-only verification loop для Discord desktop non-voice.

## Что изменилось

- Добавлен адаптер `gui/zap2_gui/adapters/discord_verification.py`.
- Добавлен CLI-план проверки:

```bash
PYTHONPATH=gui python -m zap2_gui.app --discord-verification-plan
```

- Добавлен CLI для создания owner report template:

```bash
PYTHONPATH=gui python -m zap2_gui.app --discord-verification-template
```

- Шаблон создаётся в:

```text
.zap2/verification/discord-non-voice-owner-check.md
```

- Вкладка Blockcheck lab получила кнопку `Discord checklist`, которая показывает
  тот же verification loop без запуска сетевых действий.
- Добавлен документ `docs/V04_DISCORD_OWNER_VERIFICATION.md`.
- Обновлены roadmap, Discord plan, Strategy docs, Service target docs,
  Versioning и README.
- Добавлены тесты `tests/test_discord_owner_verification_loop.py`.

## Граница Stage 6

Проверяется только Discord desktop non-voice:

- login/session;
- gateway;
- список серверов и каналов;
- текстовые чаты;
- CDN/media.

Не входит в критерий успеха:

- voice channels;
- звонки;
- screen share;
- UDP/STUN discovery;
- автоматическая одновременная работа YouTube и Discord одной стратегией.

## Проверки

```bash
PYTHONPATH=gui python -m pytest \
  tests/test_discord_owner_verification_loop.py \
  tests/test_service_aware_strategy_export.py \
  tests/test_blockcheck_gui_lab.py \
  tests/test_service_target_presets.py \
  tests/test_service_target_hostlist_alignment.py \
  tests/test_v04_alpha_patch_roadmap.py \
  tests/test_documentation_language.py -q

python -m compileall -q gui tests
```
