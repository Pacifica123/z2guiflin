# Документация z2guiflin

Этот файл является основной точкой входа. Документы разделены по назначению, а не по номеру старого stage.

## Сначала читать

1. `PROJECT_STATUS.md` — что реально работает в текущей v0.7/P04 линии и где проходит граница проекта.
2. `V04_RELEASE.md` — почему состояние поднято до v0.4 без обещания универсальной стратегии.
3. `KNOWN_GAPS_CHECKLISTS.md` — текущие недостатки по горизонтальным категориям.
4. `SAFETY_AND_PRIVILEGE_BOUNDARY.md` — границы `sudo`, `nftables`, процессов и секретов.
5. `PROJECT_STRUCTURE.md` — карта каталогов и ответственность слоёв.

## Архитектура и правила

- `DEVELOPMENT_STRATEGY.md` — порядок развития и принятия решений.
- `P04B_EXECUTION_PLAN.md` — resource-location contract, immutable execution Plan и compatibility aliases.
- `P04C_ACTION_DISPATCHER.md` — canonical ActionContract dispatcher, legacy CLI translator и contradiction gate.
- `VERSIONING.md` — правила версий, принятый v0.7 baseline и P04d/RC4 candidate toward v0.8.
- `DOCUMENTATION_LANGUAGE.md` — язык и границы перевода.
- `SOURCE_ALIGNMENT.md` — связь с bol-van, loop-uh, Flowseal и другими reference-снимками.
- `ADR_P04_DOMAIN_ONTOLOGY.md` — canonical nouns, legacy aliases и ActionContract boundary.
- `P04_REFORENSICS.md`
- `P04D_ACTION_CONTRACT_CLOSURE.md` — финальное закрытие ActionContract coverage/roundtrip/lint для RC4 — post-P03f assumptions delta, REP/CLI/S-INSTALL evidence и recompiled DAG.
- `PRESET_PROFILE_ARCHITECTURE.md` — модель `пресет -> профили`.
- `RUNTIME_LIFECYCLE.md` — общий lifecycle runtime.
- `SAFETY_AND_PRIVILEGE_BOUNDARY.md` — правила безопасности.

## Пользовательские компоненты

- `BLOCKCHECK_GUI.md` — Blockcheck Lab и подбор стратегий.
- `PRESET_CONSTRUCTOR.md` — конструктор пресетов и его ограничения.
- `UNIVERSAL_HAR_WORKBENCH.md` — универсальный разбор HAR.
- `GUI_SHELL.md` — устройство GUI.
- `GUI_RUNTIME_CONTROLS.md` — runtime controls.
- `TUNNEL_GUI_PROFILE_TABLE_AND_UNIFIED_TOGGLE.md` — управление туннелем в GUI.
- `TUNNEL_GUI_CORE_START_AND_XHTTP.md` — внешний tunnel core и XHTTP-related параметры.

## Runtime и сборка

- `CORE_INVENTORY.md`, `CORE_BUILD_MAP.md`, `LOCAL_BUILD_ADAPTER.md` — ядро и сборка.
- `DEFAULT_WORKFLOW.md`, `DEFAULT_BUILD_WORKFLOW.md` — основной запуск.
- `RUNTIME_STATE_AND_CONFIRMATION.md` — plan/hash/confirmation.
- `RUNTIME_APPLY_REVERT.md` — owned-правила `nftables`.
- `RUNTIME_SESSION_RUNNER.md` — управляемая сессия `nfqws2`.
- `RUNTIME_OWNERSHIP_RECOVERY.md` — workspace owner identity, checked nft transaction, process identity и reconciliation/recovery.
- `SECURITY_IPBLOCKLIST.md` — изолированная threat-IP policy, LKG update и explicit timer.
- `RUNTIME_SERVICE_PLANS.md` — планы service mode; это ещё не готовый пользовательский сервис.

## Диагностика Discord и исторические исследования

Файлы с `DISCORD_*`, `V04_ALPHA_*`, `V04_DISCORD_*` и `STAGE*` сохраняют ход исследований и описание отдельных реализованных инструментов. Номера stage являются историческими идентификаторами и не определяют текущую версию продукта.

Для текущего решения сначала использовать `PROJECT_STATUS.md`, `V04_RELEASE.md` и `KNOWN_GAPS_CHECKLISTS.md`. К stage-файлам обращаться только за деталями конкретного адаптера, команды или наблюдения.

## Reference и upstream

- `docs/reference/` — локальные сводки старого проекта и Windows GUI.
- `references/external/` — машинно-читаемые reference-снимки и краткие выдержки.
- `core/zapret2/docs/` — неизменяемая документация upstream bol-van.
- `meta_tools/devctl/` — снимок инструмента разработки; его upstream-файлы не являются пользовательской документацией z2guiflin.

## Аудит

`DOCUMENTATION_AUDIT.md` фиксирует результаты генеральной уборки, правила актуальности и перечень проверенных групп документов.
