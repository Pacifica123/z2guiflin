# Конспект Windows GUI reference

Архив Windows GUI не является implementation base для Linux-перезапуска. Это product reference: он показывает, какие user-facing affordances полезны вокруг `zapret`/`zapret2`.

## Идеи, которые нужно сохранить

### Философия toolbox/apothecary

Reference GUI представляет стратегии как набор доступных средств, а не как одну универсальную magic button. Linux-продукт должен сохранить эту идею: несколько профилей, видимые trade-offs и возможность владельца добавлять или менять strategies.

### Presets, profiles и ordering

В Windows-дереве есть богатая терминология вокруг presets, profiles, folders, ordering, raw editors и strategy resolution. Linux-перезапуск должен со временем моделировать strategies как first-class data, а не как hard-coded buttons.

### Diagnostics-first workflow

Важные области reference включают blockcheck, DNS diagnostics, logs, support bundles и runtime health checks. Для Linux первая версия должна предпочитать read-only diagnostics до privileged apply/start actions.

### Идея orchestrator/scanner

Reference содержит концепции strategy scanning/orchestration. Linux-продукт позже может использовать похожую идею как developer tool: пробовать candidate strategies, записывать результаты и помогать выбрать next action.

### Явное runtime state

Windows GUI содержит много модулей для process/runtime monitoring, startup coordination, workers и log tailing. Linux должен сохранять runtime state явным и inspectable, а не прятать его за единственной меткой “installed/not installed”.

### Settings и host/domain management

DNS, hosts, hostlists, ipsets, blobs и program settings — продуктовые области, которые стоит сохранить концептуально. Их Linux-реализация должна быть адаптирована к Linux paths и privilege boundaries.

## Идеи, которые нельзя копировать напрямую

- Windows registry assumptions;
- Task Scheduler/NSSM service model;
- WinDivert-specific runtime behavior;
- Defender/antivirus-specific UX;
- Windows packaging и PyInstaller assumptions;
- прямые Windows paths и batch-file strategy execution.

## Перевод в Linux-архитектуру

| Reference idea | Направление Linux-перезапуска |
| --- | --- |
| Presets/profiles | Project/user strategy registry |
| Blockcheck | Сначала read-only diagnostics, позже controlled active checks |
| Autostart/service controls | Позже owner-confirmed systemd/user-service plans |
| Logs/support bundle | Экспорт local diagnostic report |
| Raw preset editing | Text/config editor with validation |
| Strategy scan | Developer-owner experiment runner |

Reference ценен формой продукта, а не тем, что его Windows internals нужно переносить один-в-один.
