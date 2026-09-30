# Аудит документации

## Итог

Генеральный аудит выполнен для project-authored Markdown-файлов текущего снимка. Основные проблемы были такими:

- корневой README превратился в длинный журнал stage и перестал описывать текущий продукт;
- версия продолжала называться `v0.4-alpha`, хотя основной контур уже сформирован;
- несколько документов полностью или преимущественно были на английском;
- планы, результаты экспериментов и актуальные инструкции лежали на одном уровне;
- отсутствовал единый список недостатков относительно upstream и Windows-проектов;
- тест языка проверял только вручную выбранную часть файлов.

## Выполненные действия

- Создан `docs/README.md` как единая точка входа.
- Корневой README сокращён и переписан под v0.4.
- Созданы `PROJECT_STATUS.md`, `V04_RELEASE.md` и `KNOWN_GAPS_CHECKLISTS.md`.
- Переписаны `VERSIONING.md`, `DEVELOPMENT_STRATEGY.md`, `DOCUMENTATION_LANGUAGE.md` и `PROJECT_STRUCTURE.md`.
- Англоязычные project-authored документы переведены или заменены русскими ретроспективами.
- Stage ID отделены от версии продукта.
- Проверка русского языка расширена на все project-authored `.md` вне vendored upstream.
- Проверены относительные Markdown-ссылки.

## Классы документов

### Актуальные правила и статус

```text
README.md
docs/README.md
docs/PROJECT_STATUS.md
docs/V04_RELEASE.md
docs/VERSIONING.md
docs/DEVELOPMENT_STRATEGY.md
docs/DOCUMENTATION_LANGUAGE.md
docs/PROJECT_STRUCTURE.md
docs/SAFETY_AND_PRIVILEGE_BOUNDARY.md
docs/SOURCE_ALIGNMENT.md
docs/KNOWN_GAPS_CHECKLISTS.md
```

Эти файлы должны обновляться при каждом изменении версии, архитектуры или границы безопасности.

### Справка по действующим компонентам

```text
BLOCKCHECK_GUI.md
BUILD_DEPENDENCY_PREFLIGHT.md
CORE_BUILD_MAP.md
CORE_INVENTORY.md
DEFAULT_BUILD_WORKFLOW.md
DEFAULT_RUNTIME_PLAN_GENERATOR.md
DEFAULT_STRATEGY_IMPORT.md
DEFAULT_WORKFLOW.md
GUI_*.md
LAUNCH_*.md
LOCAL_BUILD_ADAPTER.md
META_TOOLS.md
NFQUEUE_PRIVILEGE_ORDER.md
PRESET_CONSTRUCTOR.md
PRESET_PROFILE_ARCHITECTURE.md
RUNTIME_*.md
SERVICE_COVERAGE_POLICIES.md
SERVICE_TARGET_PRESETS.md
STRATEGIES.md
TUNNEL_*.md
UNIVERSAL_HAR_WORKBENCH.md
WORKSPACE_PROFILES.md
```

Номера stage внутри этих файлов являются историей появления функции. Описание текущего поведения должно оставаться верным.

### История исследований v0.4

```text
DISCORD_COMMUNITY_*.md
DISCORD_DNS_EDGE_DIAGNOSTICS.md
DISCORD_ENDPOINT_DISCOVERY.md
DISCORD_FLOWSEAL_WINDOWS_REFERENCE.md
DISCORD_HAR_DISCOVERY.md
DISCORD_OBSERVATION_MATRIX*.md
DISCORD_PRETLS_*.md
DISCORD_SYN_DATA_*.md
DISCORD_TUNNEL_SOCKS_VLESS_PLAN.md
DISCORD_VOICE_SOURCE_BRIDGE.md
EXTERNAL_REFERENCE_AUDIT.md
EXTERNAL_REFERENCE_CANDIDATE_STRATEGIES.md
V04_ALPHA_PATCH_ROADMAP.md
V04_DISCORD_DESKTOP_PLAN.md
V04_DISCORD_OWNER_VERIFICATION.md
V2RAYNG_REFERENCE_NOTES.md
WINDOWS_COMMUNITY_PRESET_PORTING.md
ZAPRET2_CORE_BLOCKCHECK_NOTES.md
```

Эти документы сохраняют причины решений, owner evidence и команды отдельных экспериментов. Они не являются текущим roadmap после выпуска v0.4.

### Локальные reference-сводки

```text
docs/reference/legacy_project_digest.md
docs/reference/windows_gui_feature_digest.md
references/external/
```

Сводки могут описывать внешний проект, но должны иметь русское объяснение того, зачем материал нужен z2guiflin.

### Vendored upstream

```text
core/zapret2/docs/
core/zapret2/blockcheck2.d/**/README.txt
core/zapret2/nfq2/windows/res/howto.txt
```

Эти файлы принадлежат upstream bol-van и не переводятся локально. Их изменение допускается только как часть контролируемого upstream import.

### Инструментальный upstream

```text
meta_tools/devctl/README.upstream.md
meta_tools/devctl/docs/
```

Это reference-снимок devctl. Пользовательские правила z2guiflin не должны зависеть от языка этих файлов.

## Проверка актуальности

Документ считается актуальным, если:

- указанная команда существует в CLI или явно помечена как историческая;
- файл не обещает гарантированный обход конкретного сервиса;
- stage ID не используется как текущая версия продукта;
- привилегированные действия описаны через owner confirmation;
- Windows flags не представлены как исполняемые Linux options;
- секреты и приватные URI не включены в примеры;
- текст проекта содержит русское объяснение.

## Оставшийся долг

Полное физическое перемещение stage-файлов в `docs/history/` не выполнено, чтобы не ломать существующие ссылки, тесты и привычные пути. После v0.4 это можно сделать отдельной миграцией с redirect-файлами или массовым обновлением ссылок.

Автоматическая проверка пока не подтверждает, что каждая упомянутая CLI-команда всё ещё существует. Такой lint указан в `KNOWN_GAPS_CHECKLISTS.md`.
