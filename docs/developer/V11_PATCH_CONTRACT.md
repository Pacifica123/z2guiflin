# v1.1 — диагностика запуска и Overview

База: предоставленный post-P07 commit a0bd474. Владелец проекта объявил v1.0 закрытой; это решение о версии, не выдуманный новый owner/live/VM receipt. v1.1 исправляет подтверждённый GUI defect и путь сборки автором.

Контракт: невыбранный VLESS не порождает ошибку отсутствующего профиля или core; все registry rows остаются в подробном выводе. Классификация получает выбранные component IDs и исключает невыбранные строки из evidence. Отсутствующий/устаревший core receipt блокирует start до подтверждения и sudo; готовность использует тот же verify_core_bundle, что execution. Overview показывает причину и отдельную «Собрать ядро», не запускает build без просмотра плана/подтверждения. Ошибки receipt нельзя исправлять созданием фиктивного receipt. Receipt от clean staged build остаётся обязательным даже для собственного исходного проекта.

Визуал: видимые состояния checkbox в светлой/тёмной/custom теме, подписи основной кнопки, скрытые VLESS inputs при отключённом VLESS, future placeholders только в Developer mode. Не выбран ни один компонент → запуск недоступен. Запущенный компонент сохраняет stop; build readiness не мешает штатной остановке.

Автор создаёт archive+PKGBUILD из текущего checkout одним script; makepkg выполняется в output directory, installation только по явному --install. Исходный GUI запускается bash ./run.sh без обязательного packaging. Пакет не переносит runtime или native binaries из checkout; installed workspace требует свою сборку ядра.

Проверка: воспроизводимый captured output пользователя; selected/unselected VLESS; binary без receipt; корректный receipt; no partial start при blockers; Qt widget states/clicks, light/dark/custom rendering; generated references; полный неизменённый L0–L2 corpus; exact devctl roundtrip и source-release byte reproducibility. Native makepkg/GUI desktop/live network в контейнере не объявляются PASS.

P07 qualification profile, freeze и PC сохранены как исторические. Current v1.1 profile в v11-contract.json сохраняет старые compatibility probes/partition requirements для аудита; matrix не переоткрывает принятое владельцем v1.0. Version/tag не присваиваются runner автоматически.
