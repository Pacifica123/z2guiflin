#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

if [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
    PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python)"
else
    printf '%s\n' "Python 3 не найден." >&2
    exit 127
fi

export PYTHONPATH="$ROOT_DIR/gui${PYTHONPATH:+:$PYTHONPATH}"

if [[ $# -eq 0 ]]; then
    set -- --gui
elif [[ "$1" == "--cli" ]]; then
    shift
fi

for argument in "$@"; do
    if [[ "$argument" == "--gui" ]]; then
        if ! "$PYTHON_BIN" -c 'import PyQt6' >/dev/null 2>&1; then
            cat >&2 <<'MESSAGE'
PyQt6 не найден в выбранном Python.
Arch/Manjaro: sudo pacman -S python-pyqt6
Виртуальное окружение: python -m pip install -e '.[gui]'
MESSAGE
            exit 2
        fi
        break
    fi
done

exec "$PYTHON_BIN" -m zap2_gui.app "$@"
