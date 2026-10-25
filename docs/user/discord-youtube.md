# Discord и YouTube: что проверяется и почему

Профили Blockcheck «Discord desktop» и «YouTube» описывают сервис фазами. Фазы идут через И: стратегия
считается полной, только если прошла все обязательные. Адреса внутри одной фазы — ИЛИ: хватает любого.

## Discord desktop

| Фаза | Адреса | Обязательна |
|---|---|---|
| Updater/bootstrap | updates.discord.com, stable.dl2.discordapp.net | да |
| App/API | discord.com | да |
| Gateway | gateway.discord.gg | да |
| Картинки и превью | media.discordapp.net, images-ext-1.discordapp.net | да |
| Вложения и файлы | cdn.discordapp.com | да |
| Voice | discord.media и любые *.discord.media | нет |
| Invite | discord.gg | нет |

- **Войс — следствие.** На практике стратегия, открывшая приложение, gateway и картинки, даёт и рабочий войс,
  поэтому отдельной фазы для него при сканировании нет. Если войс всё же не работает — `--discord-voice-profiles`.
- **Вложения — своя фаза.** Раньше cdn.discordapp.com был ИЛИ-альтернативой media.discordapp.net, и стратегия,
  открывшая только картинки, выглядела полной, хотя `cdn.discordapp.com/attachments/` не отвечал.

### «Картинки грузятся, а вложение — NS_ERROR_TIMEOUT»

1. `ping cdn.discordapp.com` проверяет только IP по ICMP. DPI работает выше: по имени сайта в TLS (SNI)
   и по объёму данных внутри соединения. Удачный ping ничего не говорит о загрузке файла.
2. Discord открывает файлы-вложения во внешнем браузере — так устроен сам клиент. У браузера свой путь:
   Firefox может брать адрес через встроенный DoH и идти по HTTP/3 (UDP 443). Стратегия, подобранная под TCP,
   такой запрос не видит.
3. Кнопка **«Проверить вложения»** в Blockcheck lab (из checkout: `PYTHONPATH=gui python3 -m zap2_gui.adapters.discord_media_probe URL`) проходит
   DNS → TCP → TLS → HTTP → тело для media.discordapp.net, cdn.discordapp.com и вставленной ссылки на вложение
   (ПКМ по файлу → «Копировать ссылку»). Она показывает, на какой стадии всё встало:
   - TLS не завершается или сбрасывается — DPI по имени сайта: нужна другая стратегия для cdn.discordapp.com;
   - соединение открылось, а тело встало на первых ~16–20 КБ — ограничение по объёму на пути. Blockcheck такого
     не видит без `CURL_PAD`; помогает стратегия, которая проходит дальше первых килобайт, или туннель;
   - здесь всё OK, а в браузере нет — разница в браузере (DoH, HTTP/3).

## YouTube

| Фаза | Адреса |
|---|---|
| Сайт | www.youtube.com, youtube.com |
| Видео | узел rrN---sn-XXXX.googlevideo.com, запасной redirector.googlevideo.com |
| Превью | i.ytimg.com |

- Видео идёт не с youtube.com, а с узлов googlevideo, и узел у каждого провайдера свой. Перед сканом программа
  спрашивает узел у `redirector.googlevideo.com/report_mapping` и проверяет его первым. Если redirector не ответил
  или не назвал узел, проверяется сам redirector: тот же суффикс googlevideo.com в SNI, но не тот же сервер.
  Узнать узел вручную (из checkout): `PYTHONPATH=gui python3 -m zap2_gui.adapters.googlevideo_node`.
- www.youtube.com идёт первым: голый youtube.com только перенаправляет на www, и Blockcheck спотыкался о него.
- В Blockcheck lab для пресетов с фазами «Auto-skip dead target» выключен по умолчанию: проверка порта даёт ложный «мёртвый адрес».

## Hostlist

nfqws2 сам учитывает поддомены: строка `googlevideo.com` покрывает все узлы, `discord.media` — все голосовые серверы.
Конкретные узлы в hostlist не пишутся. Строка с `^` в начале отключает учёт поддоменов для этого домена.

При обновлении пакета новые домены доходят до hostlist в установленном workspace: нетронутый файл заменяется,
изменённый получает только недостающие домены в отмеченном блоке. Удалённый вами домен повторно не добавляется.
