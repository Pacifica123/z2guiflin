#!/usr/bin/env bash
# Единая точка входа тестового контура z2guiflin.
# Использование: bash meta_tools/run_tests.sh [аргументы pytest...]
# Коды выхода: код pytest; 3 — pytest недоступен; 4 — прогон загрязнил дерево.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
# shellcheck source=python_runtime.sh
source "${SCRIPT_DIR}/python_runtime.sh"

PYTHON="$(zap2_pick_python "${PROJECT_ROOT}")" || {
  echo "Не найден Python >= 3.10 (можно указать явно через ZAP2_PYTHON)." >&2
  exit 3
}

if ! PYTHONDONTWRITEBYTECODE=1 "${PYTHON}" -c 'import pytest' >/dev/null 2>&1; then
  cat >&2 <<MSG
pytest недоступен для ${PYTHON}.
Установите его одним из способов:
  sudo pacman -S python-pytest          # Arch/CachyOS
  python -m pip install -e '.[dev]'     # в venv проекта (.venv)
Либо укажите каталог с pytest через PYTHONPATH.
MSG
  exit 3
fi

cd "${PROJECT_ROOT}"
in_git=0
if git -C "${PROJECT_ROOT}" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  in_git=1
  before="$(git status --porcelain --untracked-files=all)"
fi

rc=0
PYTHONDONTWRITEBYTECODE=1 "${PYTHON}" -B -m pytest -q -p no:cacheprovider tests "$@" || rc=$?

if [[ "${in_git}" == 1 ]]; then
  after="$(git status --porcelain --untracked-files=all)"
  new_entries="$(comm -13 <(printf '%s\n' "${before}" | sort) <(printf '%s\n' "${after}" | sort) | sed '/^$/d')"
  if [[ -n "${new_entries}" ]]; then
    echo "ОШИБКА: тестовый прогон изменил рабочее дерево (тесты должны писать только в tmp_path):" >&2
    printf '%s\n' "${new_entries}" >&2
    [[ "${rc}" == 0 ]] && rc=4
  fi
fi
exit "${rc}"
