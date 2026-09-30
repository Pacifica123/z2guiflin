# Диагностика, ошибки и откат

Начните с Ctrl+K или `zap2-gui --find NFQUEUE`. Карточка действия показывает смысл, условия, эффект и права. Read/validate операции можно явно вызвать из palette; мутации проходят существующий plan/confirm workflow. Технические ID раскрываются отдельно, а page-local поиск пресетов остаётся самостоятельным.

| Симптом | Что посмотреть | Следующий безопасный шаг |
|---|---|---|
| Ядро отсутствует | Build dependencies и provenance | Подготовить build plan; проверить выбранный binary |
| Stale PID | Runtime status и ownership | Сверить идентичность; не убивать неизвестный процесс |
| nft conflict | Owner-rules reconciliation | Не удалять чужую таблицу; проверить owner marker |
| SOCKS работает, TLS падает | Current-run evidence по каждому mandatory target | Сопоставить TLS failure и core/server evidence, затем повторить свежую проверку |
| Discord не запускается | HTTPS, Gateway и navigation отдельно | Выполнить первый отсутствующий/упавший predicate |
| Транспорт не поддерживается | Core capability/preflight | Проверить совместимость core и connection; не менять протокол наугад |
| Обновление заблокировано | Installation receipt и conflicts | Остановить/reconcile runtime или сохранить пользовательские изменения отдельно |

Для отката firewall найдите «откат firewall», подготовьте owner-rules revert plan, подтвердите его ID и исполните штатно. Не используйте удаление всех nft tables или остановку по одному PID. Сервисный автозапуск в этом пакете **plan-only**: systemd unit не устанавливается и не включается.

Support export: `zap2-gui --support-bundle /path/new-support.zip`. В нём только положительно разрешённые identity/status/evidence fields; динамические ID и targets хешируются. Raw logs, URI, UUID/password/token/key material, HAR и configs не включаются. Поэтому это полезный краткий контекст проверки, а не полный лог или доказательство внешней доступности.

[Установка](../user/getting-started.md) · [Жизненный цикл](lifecycle.md) · [Справочник](../generated/reference.md).

P07 добавляет в support разрешённые Plan/Run summaries и typed log event projections, а также nextAction для ownership class. Все динамические ID/hash значения дополнительно хешируются; argv/message/detail не сериализуются. Полезность такого контекста при намеренно вызванной ошибке и отсутствие секретов оценивает отдельный reviewer: наличие ZIP не равно успешной оценке.
