# v0.4-alpha Stage 5: service-aware export и Strategy UX

Патч продолжает цикл `v0.4-alpha` после Discord hostlist/runtime alignment.
Цель Stage 5 — сделать generated strategies привязанными к service target preset,
чтобы владелец не путал YouTube и Discord результаты при выборе стратегии для
Default profile.

## Что изменилось

- `BlockcheckOptions` получил `service_target_preset_id`.
- Blockcheck plan/log теперь показывает `service target preset: ...`.
- В окружение upstream blockcheck добавляется `ZAP2_SERVICE_TARGET_PRESET` как
  локальная метка GUI/exporter; upstream script не обязан её понимать.
- Exporter читает service id из последнего successful Blockcheck log или
  безопасно infer-ит его из старых логов.
- Generated strategy id/title/summary теперь service-aware:
  `blockcheck-discord-desktop-gateway.discord.gg-...`.
- Generated JSON получает блок `serviceTarget` и `sourcePreset.serviceTargetPresetId`.
- `WorkspaceStrategy` и CLI/GUI Strategy UX показывают service target label.
- Добавлены тесты service-aware export и sequential candidate inference.

## Что не изменилось

- YouTube baseline остаётся default.
- Runtime не получает hidden auto-switching.
- Default profile по-прежнему использует одну явно выбранную strategy.
- Одновременная работа YouTube и Discord не гарантируется.
- Discord voice/UDP не реализуется в этом stage.

## Проверки

```bash
PYTHONPATH=gui python -m pytest \
  tests/test_service_aware_strategy_export.py \
  tests/test_blockcheck_gui_lab.py \
  tests/test_service_target_presets.py \
  tests/test_workspace_profiles_and_strategies.py \
  tests/test_service_target_hostlist_alignment.py \
  tests/test_v04_alpha_patch_roadmap.py \
  tests/test_documentation_language.py -q

python -m compileall -q gui tests
```
