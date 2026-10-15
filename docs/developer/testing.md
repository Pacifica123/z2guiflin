# Тестовый контур

## Точка входа

Единственный поддерживаемый способ запуска тестов:

```bash
bash meta_tools/run_tests.sh            # весь набор
bash meta_tools/run_tests.sh -k launch  # дополнительные аргументы передаются в pytest
```

Скрипт работает из любого каталога: выбирает Python >= 3.10 через
`meta_tools/python_runtime.sh` (`ZAP2_PYTHON` → `.venv` → системный Python),
проверяет доступность pytest и запускает
`python -B -m pytest -q -p no:cacheprovider tests` из корня проекта.
`PYTHONPATH` из окружения учитывается.

Коды выхода: код pytest; `3` — нет pytest или подходящего Python
(подсказка: `sudo pacman -S python-pytest` или `pip install -e '.[dev]'`);
`4` — тесты прошли, но прогон оставил новые файлы в рабочем дереве git.

Раннером является pytest (зависимость `dev` в `pyproject.toml`);
`python -m unittest discover` не поддерживается.

## Политика пропусков

Тесты, требующие PyQt6, пропускаются явно (`pytest.importorskip` или
`skipif` по `importlib.util.find_spec("PyQt6")`) с причиной в отчёте
(`-rs`). Пропуск не считается успешной проверкой GUI: на машине с PyQt6
эти тесты обязаны выполняться.

## Чистота дерева

Тесты пишут только во временные каталоги (`tmp_path`). Скрипт сравнивает
`git status --porcelain` до и после прогона и падает при появлении новых
записей.

## devctl

Проверки devctl должны вызывать `bash meta_tools/run_tests.sh`, а не pytest
напрямую.
