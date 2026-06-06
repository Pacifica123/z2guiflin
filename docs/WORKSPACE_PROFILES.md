# Workspace-профили

Stage 7 вводит понятие **workspace-профиля**. Это не системный профиль Linux и не install preset. Это JSON-описание рабочего пространства владельца: какая стратегия выбрана, какой build target считается основным и какие локальные hostlists относятся к этому набору данных.

## Где лежат профили

```text
profiles/
  README.md
  default.json
  hostlists/
    default.hosts
  examples/
    lab-readonly.json
```

Активные профили для приложения лежат прямо в `profiles/*.json`. Файлы в `profiles/examples/` являются примерами формы данных и не выбираются как default. Такой вариант намеренно прост: владелец может открыть JSON глазами, поправить его вручную и понять, что именно будет читать GUI.

## Что описывает профиль

`profiles/default.json` содержит:

- `id` — стабильный идентификатор профиля;
- `title` и `description` — человекочитаемое описание;
- `strategyId` — ссылка на стратегию из `strategies/`;
- `buildTarget` — цель из local build adapter: `all`, `nfqws2`, `ip2net`, `mdig` или `clean`;
- `hostlists` — ссылки на локальные файлы внутри workspace;
- `safety` — границы Stage 7: read-only проверки, отсутствие `sudo`, отсутствие service/firewall mutation;
- `notes` — пояснения для владельца и будущего GUI.

## Safety boundary Stage 7

Профиль пока ничего не применяет. Он только связывает данные. Автоматические проверки и CLI-команды Stage 7 могут:

- прочитать профиль;
- проверить, что `strategyId` существует;
- проверить, что `buildTarget` поддерживается build adapter;
- проверить, что hostlist-файлы находятся внутри workspace;
- показать профиль в текстовом виде.

Они не могут запускать `make`, `sudo`, `systemd`, firewall-операции или upstream installer scripts. Реальные run/apply/session plans появятся отдельными будущими стадиями и должны требовать явного подтверждения владельца.

## CLI

```bash
PYTHONPATH=gui python -m zap2_gui.app --list-profiles
PYTHONPATH=gui python -m zap2_gui.app --show-profile default
```

Эти команды являются read-only. Они нужны, чтобы будущая вкладка `Стратегии` получила тот же источник данных, что и тесты.
