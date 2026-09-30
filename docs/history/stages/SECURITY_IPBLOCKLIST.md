# Security IP blocklist

Опциональная security-policy использует агрегированные списки `bitwire-it/ipblocklist` для блокировки известных вредоносных IP. Она намеренно **не** смешивается с zapret/NFQUEUE: DPI bypass и threat blocking имеют разных владельцев, правила и failure model.

## Модель

- функция по умолчанию выключена;
- outbound blocking включается в config отдельно и ограничен `meta skuid` UID владельца workspace;
- inbound blocking является host-wide `INPUT` policy и требует отдельного явного включения;
- используется отдельная workspace-owned таблица `inet zap2sec_*` с owner marker;
- никаких `queue num`/NFQUEUE правил security policy не создаёт;
- updater скачивает **только включённые направления**: default outbound-only не тянет многомиллионный `inbound.txt`;
- upstream input валидируется потоково и разделяется на IPv4/IPv6 без попытки держать/`collapse_addresses()` весь многомиллионный набор в памяти;
- новый validated cache записывается как immutable generation с SHA-256 по файлам; маленький `cache.json` атомарно переключается на generation только после полной проверки;
- apply повторно проверяет SHA-256 active generation и выполняет `nft --check -f` перед одним `nft -f` batch;
- update/apply/remove сериализованы workspace lock, поэтому periodic timer и ручная команда не могут менять один cache/firewall lifecycle одновременно;
- при сетевой ошибке periodic refresh использует только уже валидированный last-known-good generation; если его нет, firewall не меняется;
- public DNS resolvers и текущие resolvers из `/etc/resolv.conf` получают owner-table `accept` до security `drop`. Это сохраняет resolver exclusions без дорогостоящего разрезания миллионов CIDR при каждом update;
- inbound имеет отдельный высокий `maxEntries` guard и остаётся opt-in: это host-wide policy и upstream набор значительно тяжелее outbound;
- неизвестная/чужая таблица с совпавшим именем не перезаписывается и не удаляется.

Сами `inbound.txt`/`outbound.txt` в репозитории не вендорятся. Это внешние агрегированные данные; их лицензирование и лицензии исходных провайдеров остаются за upstream-источниками. Локальный config хранит HTTPS URLs и параметры policy.

## Локальный workflow

Создать config и включить только outbound policy:

```bash
./run.sh --security-blocklist-enable
```

Опционально разрешить host-wide inbound policy:

```bash
./run.sh --security-blocklist-enable-inbound
```

Обновить active last-known-good generation без изменения firewall:

```bash
./run.sh --security-blocklist-update
```

Применить validated generation локально с привилегиями:

```bash
sudo -E ./run.sh --security-blocklist-apply
```

Проверить локальный status:

```bash
./run.sh --security-blocklist-status
```

## Periodic refresh

Timer не устанавливается скрыто. Сначала config должен быть создан обычным владельцем workspace. План unit-файлов можно посмотреть без установки:

```bash
./run.sh --security-blocklist-timer-plan
```

Затем владелец явно устанавливает workspace-scoped timer:

```bash
sudo -E ./run.sh --security-blocklist-install-timer
```

Интервал берётся из `updateIntervalSeconds` config (по умолчанию 7200 секунд) с randomized delay. Service получает ограничивающие systemd options (`NoNewPrivileges`, `PrivateTmp`, read-only home/system с write-доступом только к workspace `.zap2`). Установка unit-файлов атомарная; failure при `systemctl enable --now` удаляет созданные units и делает `daemon-reload`.

Удаление timer не изменяет firewall:

```bash
sudo -E ./run.sh --security-blocklist-remove-timer
```

Выключение policy меняет config и точечно удаляет только доказанно owned security table:

```bash
sudo -E ./run.sh --security-blocklist-disable
```
