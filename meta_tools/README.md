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
