# 2026-10-25-discord-youtube-profiles — профили Discord и YouTube по механизму, иконки, 1.4.0

Один патч с фичами и подъёмом версии (по `docs/VERSIONING.md` фичи поднимают minor: 1.3.0 → 1.4.0).

## Что было не так (механизм, а не рецепт)

- **Вложения Discord.** В профиле Blockcheck фаза CDN/media считала `cdn.discordapp.com`, `media.discordapp.net`,
  `discord.media`, `discordapp.net` ИЛИ-альтернативами. Стратегия, открывшая только картинки (media), проходила фазу,
  хотя вложения (`cdn.discordapp.com/attachments/`) не качались. Отсюда «Discord пробит, войс есть, а файл — NS_ERROR_TIMEOUT».
  ping при этом ничего не доказывает: ICMP проверяет только IP, а DPI работает по SNI и объёму внутри TCP.
- **YouTube.** Профиль проверял только `youtube.com`/`www.youtube.com`, причём голый youtube.com первым (он лишь
  перенаправляет на www, и auto-skip dead target на нём спотыкался). Видео идёт с узлов `rrN---sn-XXXX.googlevideo.com`,
  разных у каждого провайдера; их профиль не проверял вовсе.
- **Hostlist.** Сверка «цель покрыта hostlist» шла точным совпадением, а nfqws2 сам учитывает поддомены (`^` отключает).
- **Домены не доходили до пользователя.** `profiles/` — пользовательский сид: при обновлении пакета он не трогается,
  поэтому новые домены в `default.hosts` до установленного workspace не доезжали.

## Что сделано

- `models/service_targets.py`:
  - «Discord desktop non-voice» → **«Discord desktop»** (id `discord-desktop` прежний, `non_voice=False`). Фазы: updater → app/API →
    gateway → **картинки** (media, images-ext-1) → **вложения** (cdn.discordapp.com, отдельная обязательная фаза) → voice
    (`*.discord.media`, необязательна: войс считается следствием рабочей стратегии) → invite (необязательна).
  - **YouTube** — цепочка фаз: сайт (www первым) → видео (googlevideo) → превью (i.ytimg.com), scan-all-targets.
  - Фаза может иметь `match_suffixes` и `dynamic`: хост, найденный перед сканом, считается альтернативой своей фазы.
  - Сверка с hostlist по правилу nfqws2 (`hostlist_covers_host`), поддержка `^`.
  - `infer_service_target_preset_id`: подмножество целей пресета (в т.ч. старый «youtube.com www.youtube.com» и узел googlevideo) остаётся за пресетом.
- `adapters/googlevideo_node.py`: узел googlevideo из `redirector.googlevideo.com/report_mapping` (один HTTPS-запрос, 4 с);
  при отказе — честный откат на redirector. Blockcheck lab вставляет узел перед redirector в фазу «Видео».
- `adapters/discord_media_probe.py` + кнопка **«Проверить вложения»** (Blockcheck lab): DNS → TCP → TLS → HTTP → тело для
  media.discordapp.net, cdn.discordapp.com и вставленной ссылки на вложение; показывает, на каком байте встал поток
  (обрыв на первых ~16–20 КБ — объёмное ограничение, которое Blockcheck без CURL_PAD не видит). Объясняет, что Discord
  открывает вложения во внешнем браузере (свой DoH/HTTP3). Только чтение, без sudo.
- `profiles/hostlists/default.hosts`: Discord — discord.app/.co/.dev/.gift/.new, discordstatus.com, dis.gd, discordsays.com,
  discordactivities.com, discord-attachments-uploads-prd.storage.googleapis.com (загрузка вложений); YouTube —
  youtube-nocookie.com, youtubei.googleapis.com, ggpht.com, yt3.googleusercontent.com. Узлы googlevideo не пишутся: их покрывает `googlevideo.com`.
- `distribution.py`: при обновлении hostlist-сиды (`profiles/hostlists/*.hosts|*.txt`) нетронутые заменяются, изменённые
  получают недостающие домены в отмеченном блоке; предложенные домены записываются в receipt (`seedOffers`) и повторно
  не добавляются, так что удалённый владельцем домен не возвращается.
- Иконки: `models/service_icons.py` + `assets/icons/services/{discord,youtube}.svg`. Пресеты (до двух иконок у названия:
  цель Blockcheck и название важнее доменов), профили в таблице, выбор service target в Blockcheck, кнопки Discord,
  буквенные значки DNS-провайдеров в фирменных цветах (логотипы не копируются).
- Blockcheck lab: «Auto-skip dead target» выключается для всех пресетов с фазами, не только для Discord.
- `docs/user/discord-youtube.md` — что проверяется и почему, разбор «картинки есть, вложение — таймаут».
- Версия **1.4.0** во всех привязках (pyproject, `__init__` с `PRODUCT_LABEL = "v1.4"` и
  `DEVELOPMENT_LINE = "v1.4 Discord/YouTube service profiles and icons"`, v11-contract, freeze, тесты, generated reference,
  `dist/arch/1.4.0`); доска: новая карточка в «Ждёт хоста», комментарии к карточкам Discord-медиа и версии.

## Не вошло и почему

- `app.py` и сгенерированные bindings — «preserved authorities» контракта v11; новые флаги CLI в них не добавлялись.
  Probe и узел googlevideo доступны из GUI и как модули: `PYTHONPATH=gui python3 -m zap2_gui.adapters.discord_media_probe URL`,
  `... -m zap2_gui.adapters.googlevideo_node`. CLI `--blockcheck-run` для YouTube по-прежнему с auto-stop guard.
- Формат ответа report_mapping с этой машины не проверен (сеть закрыта): разбирается вариант `=> sn-…`; если redirector
  вернёт имя кластера, программа скажет об этом и проверит redirector.
- hCaptcha (вход в Discord) в hostlist не добавлен: сторонний домен, лишний сопутствующий эффект.

## Проверки

- `tests/test_discord_youtube_profiles.py` (13): правило поддоменов и `^`, покрытие hostlist, разбор report_mapping и откаты,
  вставка узла в фазу и учёт его в покрытии, «media без вложений не проходит», классификация обрыва тела, слияние hostlist-сида
  (замена, дописывание, удалённое не возвращается), иконки и значки DNS.
- Закреплённые ожидания обновлены: состав и порядок целей YouTube/Discord, политика YouTube, заголовок «Discord desktop».
- `bash meta_tools/run_tests.sh`, `check_board.py`, freeze и generated reference пересчитаны.
