# Patch summary

v0.4 stage8j-r1: исправление usertest hot-swap, selection strat_collection и flat runtime UI.

- Исправлен фактический crash hot-swap: `GuiPrivilegedResult` имеет контракт `.ok`; адаптер больше не обращается к отсутствующему `.success`. Для обратной совместимости у результата добавлен read-only alias `.success -> .ok`.
- Сохранён транзакционный порядок `stop -> select -> start -> rollback`: ошибка GUI больше не возникает после уже выполненного stop.
- Overview получает публичный `refresh_runtime_state`; MainWindow вызывает его при переходе на страницу. После смены preset состояние больше не остаётся визуально старым до ручного refresh.
- Локальный список presets сохраняет текущую строку до `clear()`. strat_collection хранит `strat_selected_id` и восстанавливает строку после refresh/search вместо безусловного `selectRow(0)`.
- Кнопка применения стала контекстной для strat_collection. Однозначно переносимые записи можно превратить в owner-managed Zapret2 preset и сразу применить через тот же hot-swap. Уже созданный порт переиспользуется.
- Автопорт намеренно консервативный: используются только явно документированные в vendored Zapret2 mappings; Windows capture flags не исполняются. Неоднозначные `split/split2/disorder*`, неизвестные payload/blob, `dup/wssize` и другие непокрытые опции блокируют автопорт с явной причиной.
- Для известных HTTP/TLS/QUIC/Discord/STUN/WireGuard профилей добавлены безопасные Zapret2 payload/filter guards; legacy auto-TTL переносится отдельно на IPv4 и IPv6.
- Runtime indicator теперь плоский: без жёлтой pill-подложки и без роли кнопки. Цвет текста состояния задаётся темой.
- Кнопка Start/Stop получила прозрачный фон, скруглённую accent-рамку и более толстый SVG-треугольник/stop glyph; сам glyph перекрашивается по semantic theme color.
- Цвета launch notification и runtime states вынесены в theme profile schema v1. Старые schema-v1 JSON темы совместимы: новые роли заполняются из base theme.
- `themes/example-custom.json` и `docs/CUSTOMIZATION.md` обновлены под новые semantic colors и поведение strat_collection.
- Добавлен regression suite `test_stage8j_r1_usertest_hot_swap_strat_ui.py`; старый тест жёстко заданных runtime background colors обновлён под theme-semantic контракт.
