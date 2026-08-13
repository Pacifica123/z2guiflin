# Patch summary

v0.4 maintenance: исправление file dependencies для импорта полного Zapret2 `.txt` preset.

- Причина сбоя `Universal V5`: preset содержит `--hostlist=lists/*` и `--ipset=lists/*`, но один TXT не содержит данные этих файлов. Ранее импорт разрешал такой preset и runtime передавал относительные пути прямо в `nfqws2`.
- Импорт теперь ищет referenced list/ipset рядом с TXT и в двух родительских каталогах. Если источник найден, файл копируется в project-owned `presets/imported-assets/txt-*/...`, а canonical runtime arg переписывается на этот путь.
- Если автопоиск не нашёл зависимости, GUI предлагает выбрать корень исходного пакета с каталогом `lists`.
- Неполный preset по-прежнему можно сохранить для редактирования, но он явно помечается `runtime ready after import: no` и metadata содержит `missingListDependencies`.
- Launch composer и Overview показывают отсутствующие strategy files как blocker; такой Zapret component больше не получает `ready=ready`.
- Default start выполняет file preflight до owner-rules apply. При missing/unsafe dependency nftables/NFQUEUE не меняются.
- Runtime копирует strategy-level `--hostlist`, `--hostlist-exclude`, `--ipset`, `--ipset-exclude` в public per-session inputs и переписывает argv на абсолютные безопасные копии, как уже делалось для profile hostlist/Lua/blob.
- Strategy parser preflight сообщает `MISSING_STRATEGY_FILE_DEPENDENCIES` без запуска `nfqws2 --dry-run`, если обязательные файлы отсутствуют.
- GUI classifier получает код `Z2-STRATEGY-FILES-MISSING`.

Проверено отдельно на исходном `Universal V5`: без companion lists обнаруживаются 37 missing dependencies и запуск блокируется до firewall apply; с синтетическим полным каталогом `lists` импортируются 37 уникальных файлов, сохраняются 37 профилей/55 actions, а runtime config не оставляет относительных `lists/*` путей.
