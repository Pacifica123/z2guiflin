# Meta tools

`meta_tools/` содержит инструменты, которые обслуживают сам процесс разработки,
патчей и рабочих областей, но не являются частью runtime/GUI Zap2.

## devctl

`meta_tools/devctl/` — исходник и документация локального конвейера патчей.
Обычный `devctl start` должен оставаться bootstrap-minimal: он не требует
`pytest`, PyQt или других dev/test-зависимостей проекта. Его обязательные checks
выполняются на базовом окружении, достаточном для самого devctl.

## UserTestSpace environment

После успешного `devctl start` post-снимок разворачивается в
`UserTestSpace/<version>/project`. Уже **внутри этого project** запускается:

```bash
bash meta_tools/uts_prepare.sh
```

Скрипт сначала инвентаризирует UTS test environment. Если `pytest >= 8` уже
доступен в host Python, используется он. Если pytest отсутствует, на Arch-like
системе скрипт сначала пытается поставить штатный пакет `python-pytest` через
`pacman`; если это невозможно, используется isolated fallback
`UserTestSpace/<version>/.uts-venv` и `pip`. Fallback находится **вне** дерева
`project/`.

При pytest-запусках всегда используются `PYTHONDONTWRITEBYTECODE=1` и
`-p no:cacheprovider`; до/после запуска удаляются только generated
`__pycache__`, `.pytest_cache`, `*.pyc`, `*.pyo` внутри UTS project.

Режимы:

```bash
bash meta_tools/uts_prepare.sh --check   # только preflight, без установки
bash meta_tools/uts_prepare.sh --p01     # P01 + tunnel regression
bash meta_tools/uts_prepare.sh --full    # весь pytest-набор
bash meta_tools/uts_prepare.sh --pytest tests/test_file.py -k case
```

`pytest` тем самым является зависимостью **UTS regression**, но никогда не
скрытым prerequisite для `devctl start`.

## Hyperpatch owner-host acceptance

После `devctl start` и перехода в созданный UserTestSpace текущий P03 можно
проверить одной командой вместо ручного выполнения build/start/status/stop
цепочки:

```bash
bash meta_tools/hyperpatch_acceptance.sh --p03
```

P03 acceptance намеренно является **исполняемым owner-host gate**, а не только
pytest-обёрткой. Он последовательно проверяет generation/inventory, P03 regression,
PyQt6, native build dependencies, staged native `nfqws2` build, build receipt v2,
реальный parser dry-run, provenance bounded privileged executor, затем временно
применяет owned nft/NFQUEUE rules, запускает `nfqws2`, проверяет живую session и
штатно выполняет stop/revert.

Если ошибка возникает после попытки runtime start, EXIT trap делает best-effort
подтверждённый stop/revert. Evidence каждого шага сохраняется в
`.zap2/runtime/acceptance/p03-<UTC timestamp>/`, а в конце автоматически
упаковывается рядом в `p03-<UTC timestamp>.zip` вместе с snapshot session/workflow/build receipt/runtime log.

Если предыдущий acceptance успел запустить runtime, но старый код не смог его
остановить, новый runner умеет безопасно восстановить **только явно указанный**
workspace перед новым canary:

```bash
bash meta_tools/hyperpatch_acceptance.sh --p03 --recover-root /absolute/path/to/old/UTS/project
```

Recovery использует текущую identity-проверку, генерирует обычный confirmed
stop/revert plan для указанного root и не сканирует/не убивает процессы других
workspace.

Финальные строки успешного прогона:

```text
HYPERPATCH ACCEPTANCE: PASS
readiness: READY_FOR_USE_WITHIN_P03
```

Такой PASS означает, что runnable-контур программы/GUI для P03 готов к
использованию **на данном owner-host**. Он не является доказательством того, что
конкретная стратегия уже обходит конкретный DPI/провайдера: внешняя
censorship-resistance проверяется отдельными traffic/strategy probes.

## P03d: переносимый owner-host acceptance для Arch-family

`hyperpatch_acceptance.sh --p03` теперь отделяет переносимое состояние проекта от host-local prerequisites.
На Manjaro/EndeavourOS/Arch при включённом по умолчанию host setup он предпочитает distro Python
`/usr/bin/python3` перед pyenv/asdf shim из `PATH`, при необходимости устанавливает `python-pyqt6`,
штатные native build-зависимости и missing/mismatch bounded executor, а затем повторно проверяет их.
Автоисправление не применяется к `untrusted`/`unknown` privileged helper: такой случай остаётся fail-closed.

Старый `--recover-root` является host-local операцией. Если путь к старому UTS отсутствует после переезда
на другую машину, acceptance выводит `SKIP` и продолжает текущий host test. Если путь существует, recovery
остаётся строгим и обязан дойти до `PREVIOUS WORKSPACE RECOVERY: PASS`.

Для запрета любой автоматической host-подготовки используйте `--no-host-setup`.
Явный Python можно закрепить через `ZAP2_PYTHON=/path/to/python`; `run.sh`, UTS bootstrap и acceptance
используют общий selector `meta_tools/python_runtime.sh`.

### Legacy v0.4 nft collision during P03 acceptance

`hyperpatch_acceptance.sh --p03` также проверяет старую generic table `inet zap2_default`. Если она осталась после старой v0.4, скрипт не делает blind delete: `prepare_legacy_v04_migration.py` через bounded helper проверяет известный Zap2 fingerprint и отсутствие живого NFQUEUE listener, после чего пишет одноразовый consent receipt. Фактическое удаление происходит только внутри следующего confirmed atomic owner-rules apply. Active/foreign/unknown legacy state даёт FAIL без удаления.
