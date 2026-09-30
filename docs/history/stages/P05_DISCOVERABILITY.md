# P05 — поиск, справка, ошибки и состояние

Текущая версия **0.9.0rc5 / v0.9 RC5 candidate**. Последний принятый релиз — v0.8. Этот патч не создаёт owner acceptance receipt и не присваивает final 0.9.0 заранее.

Поиск: **Ctrl+K** из любой страницы. RU/EN/technical слова нормализуются, результаты ранжируются детерминированно; одна опечатка, включая перестановку соседних букв, допускается для слов от четырёх символов. Поиск пресетов на странице остаётся отдельным. Пустой запрос ничего не выполняет.

Действия выводятся из 119 ActionContracts. Настройки читаются из metadata реальных controls; понятия — из canonical ontology. Help содержит что, когда, эффект, условия и права; ID/CLI раскрываются отдельно. Каждый результат имеет точную цель: настройки фокусируют реальный control, действия и понятия — их справку в общем инспекторе. CLI-only действия не получают фиктивную GUI-кнопку исполнения.

Прямое явное выполнение разрешено только для safeInvoke + none privilege + show/list/inspect/validate + отсутствия preconditions. Оно идёт через существующий canonical dispatcher, с ограничением 30 секунд. prepare/probe/import/export/start/stop/apply/revert из palette напрямую не запускаются. Для них справка и переход ведут к текущему workflow подготовки/подтверждения; политики исполнения не меняются.

## Задачи новичка

| Вопрос | Запрос и следующий шаг |
|---|---|
| Как безопасно запустить? | `безопасно запустить` → Plan и план Default; открыть «Обзор», подготовить и подтвердить план |
| Где VLESS? | `VLESS` → соединение/план туннеля, открыть «Туннель» |
| Почему Discord не работает? | `дискорд` → понятие туннеля и evidence; раскрыть состояние, отдельно проверить SOCKS, TLS, Gateway и navigation |
| Как откатить firewall? | `откат firewall` → план отката owner-rules; проверить ID, подтвердить и выполнить через текущий workflow |
| Что такое NFQUEUE? | `NFQUEUE` → runtimeResource; справка поясняет очередь и ownership, раздел «Обзор» содержит состояние |

## Состояние и ошибки

Панель сверху раскрывается по клику; обновление читает локальные runtime/evidence данные и не запускает сетевые probes. Снимок имеет время и после изменений требует обновления. Runtime, локальный SOCKS, удалённые HTTPS/TLS targets и приложение показываются раздельно. Mandatory HTTP targets, Gateway и navigation берутся из P01; нет scalar promotion.

При чтении evidence используются текущая running session и существующая проверка run/config/receipt/core bindings. Отсутствующая, мёртвая, чужая или несовместимая session даёт UNKNOWN. Исторические файлы не выбираются по mtime. View не сохраняет пересчитанный граф. Локальный SOCKS PASS вместе с TLS FAIL/UNKNOWN виден одновременно.

Ошибки имеют cause, evidence и semantic nextAction. Existing launch banner сохраняет короткую причину; tooltip и полный текст дают следующий шаг. Нераспознанная ошибка требует просмотра, а не догадки о ремонте. Никакого автоматического удаления firewall/PID или смены транспорта.

## Приёмка одним запуском

```bash
bash meta_tools/hyperpatch_acceptance.sh --p05
```

Не запускайте shell wrapper целиком через sudo. Выбранному Python требуются pytest и PyQt6; на Arch-family это `python-pytest` и `python-pyqt6`. Runner сохраняет step logs и ZIP evidence. Выполняются P05 coverage/semantic hashes, focused GUI/model tests, generated bindings, P03 generation identity, structural gate и полный isolated regression. При любом FAIL переход останавливается.

Marker `READY_FOR_RC5_REVIEW` подтверждает deterministic candidate verification. Он не заменяет проверку задач новичка на вашей машине и не доказывает внешнюю доступность Discord/DPI bypass. После owner acceptance: new HEAD re-forensics → решение о final SemVer → P06 → P07.
