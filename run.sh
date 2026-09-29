#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

if [[ $# -eq 0 ]]; then
    set -- --gui
elif [[ "$1" == "--cli" ]]; then
    shift
fi

# shellcheck source=meta_tools/python_runtime.sh
source "$ROOT_DIR/meta_tools/python_runtime.sh"

REQUIRES_GUI=0
for argument in "$@"; do
    if [[ "$argument" == "--gui" ]]; then
        REQUIRES_GUI=1
        break
    fi
done

if (( REQUIRES_GUI != 0 )); then
    if ! PYTHON_BIN="$(zap2_pick_python "$ROOT_DIR" PyQt6)"; then
        cat >&2 <<'MESSAGE'
Не найден Python >= 3.10 с PyQt6.
Arch/Manjaro/EndeavourOS: sudo pacman -S --needed python python-pyqt6
Виртуальное окружение: python -m pip install -e '.[gui]'
Для явного выбора интерпретатора: ZAP2_PYTHON=/path/to/python ./run.sh
MESSAGE
        exit 2
    fi
else
    if ! PYTHON_BIN="$(zap2_pick_python "$ROOT_DIR")"; then
        printf '%s\n' "Python >= 3.10 не найден." >&2
        exit 127
    fi
fi

export PYTHONPATH="$ROOT_DIR/gui${PYTHONPATH:+:$PYTHONPATH}"
exec "$PYTHON_BIN" -m zap2_gui.app "$@"
