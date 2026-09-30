# Инструменты проекта v1.1

Единый профиль: bash meta_tools/hyperpatch_acceptance.sh --v11. Freeze, generated references, bindings, focused fixtures, P03 identity, structural gate и полный isolated regression выполняются в одном fail-fast/log/archive workflow. Исторические P07 checks остаются доступными для своего профиля; текущие результаты не переоткрывают закрытую владельцем v1.0.

bash meta_tools/build_local_package.sh создаёт archive/PKGBUILD из checkout в dist/arch/1.1.0. --install явно добавляет makepkg -si в том же output directory. Без --install пакет не устанавливается; скрытой native/system/network mutation нет.
