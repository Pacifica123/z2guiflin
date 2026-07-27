# Patch summary

## Title

Универсальный HAR workbench для любого ресурса

## Что изменено

- HAR GUI/CLI больше не привязан к Discord.
- Добавлен общий parser для YouTube, Discord, CDN, API и любых других HAR.
- Все observed hosts сохраняются в sanitized summary; фильтр `external-other`
  отсутствует.
- Точные динамические hosts, например `rr8---sn-*.googlevideo.com`, остаются
  Blockcheck targets и группируются по domain family.
- Добавлены безопасные error codes: `NS_BINDING_ABORTED`, `ERR_*`, `SEC_ERROR_*`.
- Разделены transport failures, browser cancellations, HTTP 4xx/5xx и просто
  новые uncovered hosts.
- Coverage сравнивается со всеми `profiles/hostlists/*.hosts`.
- Workbench пишет `targets.txt`, `hostlist-candidates.txt`,
  `blockcheck-options.json`, `candidate-index.json` и `preset-blueprint.json`.
- GUI Blockcheck Lab использует универсальный HAR workbench.
- Старые `--discord-har-*` сохранены для совместимости.
- Discord Voice профили Stage 8d не менялись и остаются отдельным блоком.

## Граница автоматизации

HAR import не запускает Blockcheck, не меняет hostlists, nftables или systemd и
не собирает исполняемый preset без подтверждённой стратегии для групп.

`NS_BINDING_ABORTED` виден в отчёте, но сам по себе не считается доказательством
DPI: browser cancellation может быть нормальной.
