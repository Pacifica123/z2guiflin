# Zap2 GUI Linux — v1.3

GUI PyQt6 управляет zapret2, immutable Plan, owned runtime и диагностикой. Он предоставляет не универсальную стратегию и не обещает работоспособность только по HTTP ответу или наличию процесса: доступность зависит от сети, core и приложения.

**Текущая версия — 1.3.0:** DNS-каталог и смена DNS, удобная страница «Пресеты» (порядок, пересечения профилей, «Кто сработает первым?», исключения, массовое удаление), Tor отдельной страницей с мостами и автообновление. 1.2.0 принесла навигацию по пути пользователя, витрину на «Главной» и подсказки «Что попробовать» после вердикта сети. v1.1 исправила ложную ошибку невыбранного VLESS, готовность сборки и визуал Overview; v1.0 закрыта владельцем проекта. Исторические P07 receipts сохраняют свою область действия и не подменяют реальные проверки нового запуска.

## Запуск автором из исходников

Из корня checkout, где находятся run.sh и pyproject.toml:

```bash
bash ./run.sh
```

Это штатный запуск без установки пакета. run.sh написан для Bash; если ваш терминал использует zsh, всё равно выполняйте `bash ./run.sh`, а не `zsh ./run.sh`. Нужны Python ≥ 3.10 и PyQt6. Не запускайте GUI через sudo.

## Создание и установка собственного пакета

Готовый опубликованный release не требуется: archive и PKGBUILD создаются из вашего текущего checkout. На Arch/Manjaro/EndeavourOS установите инструменты, затем из корня проекта:

```bash
sudo pacman -S --needed base-devel python python-pyqt6
bash meta_tools/build_local_package.sh
cd dist/arch/1.3.0
makepkg -si
```

**makepkg выполняется в dist/arch/1.3.0**, где предыдущий шаг создал PKGBUILD и zap2gui-linux-1.3.0.tar.gz. SHA закрепляет соответствие архива рецепту, а не требует внешнего одобрения вашего кода. Скрипт можно вызвать из любого каталога по абсолютному пути; output по умолчанию остаётся внутри checkout. Один workflow создания и установки: `bash meta_tools/build_local_package.sh --install`. После установки запустите `zap2-gui` из меню или терминала.

Пакетный и исходный запуск используют разные writable workspaces. Сборка пакета не является сборкой nfqws2. В Overview нажмите «Собрать ядро», проверьте зависимости и план, подтвердите сборку. Наличие старого бинарника без актуального whole-generation receipt не означает готовность; receipt создаётся настоящей staged сборкой. Автоматической установки native build dependencies или запуска стратегии здесь нет.

[Первые действия](docs/user/getting-started.md) · [Документация](docs/README.md) · [Диагностика](docs/operations/troubleshooting.md) · [Обновление/удаление](docs/operations/lifecycle.md) · [История](docs/history/README.md).

Единая приёмка v1.1: `bash meta_tools/hyperpatch_acceptance.sh --v11`. Freeze, проекции и полный L0–L2 corpus обязательны; полные logs/JUnit и compatibility matrix сохраняются. Проверки native package/live network требуют фактической owner среды и не выполняются скрытно.

Для сборки nfqws2 нужны native зависимости (пакет GUI сам ядро не компилирует):

```bash
sudo pacman -S --needed base-devel pkgconf zlib libnetfilter_queue libnfnetlink libmnl luajit
```

Overview проверяет их перед сборкой; при отсутствии показывает подробности, автоматически пакеты не устанавливает.
