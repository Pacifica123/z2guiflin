#!/usr/bin/env bash
set -Eeuo pipefail

# UserTestSpace developer/test environment bootstrap.
# IMPORTANT: this is intentionally NOT a prerequisite for `devctl start`.
# Run it only after devctl has produced UserTestSpace/<version>/project.

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd -P)"
UTS_ROOT="$(dirname -- "${PROJECT_ROOT}")"
VENV_DIR="${ZAP2_UTS_VENV:-${UTS_ROOT}/.uts-venv}"
PYTEST_SPEC="${ZAP2_UTS_PYTEST_SPEC:-pytest>=8}"

MODE="prepare"
RUN_MODE=""
RUN_ARGS=()

usage() {
  cat <<'USAGE'
Использование:
  bash meta_tools/uts_prepare.sh
      Проверить UTS-окружение и установить недостающие test/dev-зависимости.

  bash meta_tools/uts_prepare.sh --check
      Только проверить окружение. Ничего не устанавливает и не изменяет.

  bash meta_tools/uts_prepare.sh --p01
      Подготовить окружение и запустить P01+tunnel regression без cache/bytecode.

  bash meta_tools/uts_prepare.sh --full
      Подготовить окружение и запустить весь pytest-набор без cache/bytecode.

  bash meta_tools/uts_prepare.sh --pytest [pytest args...]
      Подготовить окружение и передать произвольные аргументы pytest.

Переменные:
  ZAP2_UTS_PYTHON       Явный host Python (по умолчанию: python3, затем python).
  ZAP2_UTS_VENV         Fallback venv (по умолчанию: ../.uts-venv, вне project/).
  ZAP2_UTS_PYTEST_SPEC  Pytest для pip fallback (по умолчанию: pytest>=8).
  ZAP2_UTS_NO_SYSTEM_INSTALL=1
                         Не пытаться ставить пакет через системный package manager.
USAGE
}

while (($#)); do
  case "$1" in
    --check)
      MODE="check"
      shift
      ;;
    --p01)
      RUN_MODE="p01"
      shift
      ;;
    --full)
      RUN_MODE="full"
      shift
      ;;
    --pytest)
      RUN_MODE="pytest"
      shift
      RUN_ARGS=("$@")
      break
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      printf 'Неизвестный аргумент: %s\n\n' "$1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ ! -f "${PROJECT_ROOT}/pyproject.toml" || ! -d "${PROJECT_ROOT}/tests" ]]; then
  printf 'Ошибка: %s не похож на корень z2flingui UserTestSpace project.\n' "${PROJECT_ROOT}" >&2
  exit 2
fi

pick_host_python() {
  if [[ -n "${ZAP2_UTS_PYTHON:-}" ]]; then
    if command -v -- "${ZAP2_UTS_PYTHON}" >/dev/null 2>&1; then
      command -v -- "${ZAP2_UTS_PYTHON}"
      return 0
    fi
    printf 'Ошибка: ZAP2_UTS_PYTHON=%s не найден.\n' "${ZAP2_UTS_PYTHON}" >&2
    return 1
  fi
  if command -v python3 >/dev/null 2>&1; then
    command -v python3
    return 0
  fi
  if command -v python >/dev/null 2>&1; then
    command -v python
    return 0
  fi
  printf 'Ошибка: не найден python3/python. devctl уже требует Python; проверь PATH.\n' >&2
  return 1
}

HOST_PYTHON="$(pick_host_python)"
TEST_PYTHON=""

python_version_ok() {
  "$1" - <<'PY'
import sys
raise SystemExit(0 if sys.version_info >= (3, 10) else 1)
PY
}

module_available() {
  "$1" - "$2" <<'PY'
import importlib.util
import sys
raise SystemExit(0 if importlib.util.find_spec(sys.argv[1]) is not None else 1)
PY
}

pytest_version_ok() {
  "$1" - <<'PY'
try:
    import pytest
    major = int(pytest.__version__.split('.', 1)[0])
except Exception:
    raise SystemExit(1)
raise SystemExit(0 if major >= 8 else 1)
PY
}

pytest_version() {
  "$1" -c 'import pytest; print(pytest.__version__)'
}

clean_test_artifacts() {
  # Generated Python/pytest artifacts only. Never delete source/runtime data.
  find "${PROJECT_ROOT}" -type d \( -name '__pycache__' -o -name '.pytest_cache' \) -prune -exec rm -rf -- {} + 2>/dev/null || true
  find "${PROJECT_ROOT}" -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete 2>/dev/null || true
}

try_arch_pytest_install() {
  [[ "${ZAP2_UTS_NO_SYSTEM_INSTALL:-0}" != "1" ]] || return 1
  command -v pacman >/dev/null 2>&1 || return 1

  printf '[SETUP] Arch-like host: пробую штатный пакет python-pytest через pacman...\n'
  if [[ "$(id -u)" -eq 0 ]]; then
    pacman -S --needed --noconfirm python-pytest
  elif command -v sudo >/dev/null 2>&1; then
    sudo pacman -S --needed --noconfirm python-pytest
  else
    printf '[WARN] pacman найден, но нет root/sudo; system install пропущен.\n' >&2
    return 1
  fi
}

prepare_venv_fallback() {
  local vpy="${VENV_DIR}/bin/python"
  if [[ ! -x "${vpy}" ]]; then
    printf '[SETUP] Создаю fallback UTS venv вне project/: %s\n' "${VENV_DIR}"
    if ! "${HOST_PYTHON}" -m venv "${VENV_DIR}"; then
      cat >&2 <<'ERR'
Не удалось создать fallback venv.
Проверь стандартный модуль venv для выбранного Python.
Для Arch/EndeavourOS он входит в пакет python.
ERR
      return 1
    fi
  else
    printf '[OK] fallback UTS venv уже существует\n'
  fi

  if ! module_available "${vpy}" pip; then
    printf '[SETUP] pip отсутствует в fallback venv; запускаю ensurepip...\n'
    "${vpy}" -m ensurepip --upgrade || return 1
  fi

  if ! pytest_version_ok "${vpy}"; then
    printf '[SETUP] Устанавливаю %s через pip fallback...\n' "${PYTEST_SPEC}"
    "${vpy}" -m pip install --disable-pip-version-check --no-input "${PYTEST_SPEC}" || return 1
  fi

  TEST_PYTHON="${vpy}"
  return 0
}

printf 'UTS project : %s\n' "${PROJECT_ROOT}"
printf 'Host Python : %s\n' "${HOST_PYTHON}"
printf 'Fallback venv: %s\n' "${VENV_DIR}"
printf 'Mode        : %s%s\n' "${MODE}" "${RUN_MODE:+ + ${RUN_MODE}}"

if ! python_version_ok "${HOST_PYTHON}"; then
  "${HOST_PYTHON}" --version >&2 || true
  printf 'Ошибка: требуется Python >= 3.10.\n' >&2
  exit 3
fi
printf '[OK] Python >= 3.10\n'

if pytest_version_ok "${HOST_PYTHON}"; then
  TEST_PYTHON="${HOST_PYTHON}"
  printf '[OK] pytest %s уже доступен в host Python\n' "$(pytest_version "${HOST_PYTHON}")"
else
  printf '[MISSING] pytest >= 8 отсутствует в host Python\n'
fi

if [[ -z "${TEST_PYTHON}" && -x "${VENV_DIR}/bin/python" ]] && pytest_version_ok "${VENV_DIR}/bin/python"; then
  TEST_PYTHON="${VENV_DIR}/bin/python"
  printf '[OK] pytest %s доступен в существующем fallback UTS venv\n' "$(pytest_version "${TEST_PYTHON}")"
fi

if [[ "${MODE}" == "check" ]]; then
  if [[ -n "${TEST_PYTHON}" ]]; then
    printf '[READY] UTS pytest runner: %s\n' "${TEST_PYTHON}"
    exit 0
  fi
  printf '[NOT READY] pytest runner не найден. Запусти скрипт без --check для установки.\n'
  exit 1
fi

if [[ -z "${TEST_PYTHON}" ]]; then
  set +e
  try_arch_pytest_install
  system_install_rc=$?
  set -e
  if (( system_install_rc == 0 )) && pytest_version_ok "${HOST_PYTHON}"; then
    TEST_PYTHON="${HOST_PYTHON}"
    printf '[OK] pytest %s установлен системным package manager\n' "$(pytest_version "${TEST_PYTHON}")"
  fi
fi

if [[ -z "${TEST_PYTHON}" ]]; then
  printf '[INFO] Системный pytest всё ещё недоступен; переключаюсь на изолированный pip fallback.\n'
  if ! prepare_venv_fallback; then
    cat >&2 <<ERR
Не удалось подготовить pytest ни системным package manager, ни pip fallback.
Это не блокирует `devctl start`: проблема относится только к UTS test environment.
Для EndeavourOS можно вручную выполнить:
  sudo pacman -S --needed python-pytest
а затем повторить этот скрипт.
ERR
    exit 6
  fi
fi

printf '[READY] pytest %s; runner=%s\n' "$(pytest_version "${TEST_PYTHON}")" "${TEST_PYTHON}"

# UserTestSpace is disposable/manual; keep its project tree clean for later diffs.
clean_test_artifacts

run_pytest() {
  local -a args=("$@")
  local rc
  set +e
  (
    cd "${PROJECT_ROOT}"
    export PYTHONDONTWRITEBYTECODE=1
    export PYTHONPATH="${PROJECT_ROOT}/gui${PYTHONPATH:+:${PYTHONPATH}}"
    "${TEST_PYTHON}" -m pytest -q -p no:cacheprovider "${args[@]}"
  )
  rc=$?
  set -e
  clean_test_artifacts
  return "${rc}"
}

case "${RUN_MODE}" in
  "")
    printf '\nUTS test environment готов.\n'
    printf 'P01 regression: bash meta_tools/uts_prepare.sh --p01\n'
    printf 'Полный pytest : bash meta_tools/uts_prepare.sh --full\n'
    ;;
  p01)
    run_pytest \
      tests/test_p01_network_truth_evidence.py \
      tests/test_stage7p0_discord_tunnel_plan.py \
      tests/test_stage7p1_discord_tunnel.py \
      tests/test_stage7p5_discord_tunnel_guided.py \
      tests/test_tunnel_gui_layout_and_unified_toggle.py \
      tests/test_tunnel_xhttp_core_ux.py
    ;;
  full)
    run_pytest tests
    ;;
  pytest)
    run_pytest "${RUN_ARGS[@]}"
    ;;
esac
