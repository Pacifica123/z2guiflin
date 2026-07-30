# Матрица Discord SYN-data edge-flow v2c

Статус: историческая запись Stage 7w.

Матрица создана после того, как v2b подтвердил наличие нужных hosts в runtime args, но TLS ClientHello всё ещё завершался timeout. Вместо добавления новых случайных flags были выделены отдельные гипотезы.

## Варианты

### `community-discord-syndata-edge-flow-v2c-send-only`

Минимизирует раннюю ветку и проверяет влияние простого `send` без полной комбинации v2.

### `community-discord-syndata-edge-flow-v2c-fixed-sni`

Убирает случайный SNI и использует фиксированное значение для проверки влияния `rndsni`.

### `community-discord-syndata-edge-flow-v2c-no-md5`

Убирает `tcp_md5` и проверяет, не вызывает ли он несовместимость на текущем маршруте.

### `community-discord-syndata-edge-flow-v2c-host-first`

Меняет порядок профилей, чтобы hostlist branch проверялся раньше широкого edge-IP branch.

## Почему порядок важен

`nfqws2` использует первый подходящий профиль. Широкий IP/443 профиль может перекрыть более точный host-based профиль. Поэтому изменение порядка является отдельным экспериментом, а не косметикой.

## Чистый запуск Flatpak

Перед каждой строкой нужно полностью остановить предыдущий Discord process group и убедиться, что новый процесс действительно использует ожидаемый route/runtime.

## Ручная проверка

Для каждого варианта:

```text
select strategy
-> inspect args
-> owner-confirmed start
-> endpoint/pre-TLS observation
-> Discord launch
-> record result
-> stop workflow
```

Вариант не повышается до recommended без заметного отличия от baseline.
