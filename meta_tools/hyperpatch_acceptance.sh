#!/usr/bin/env bash
set -Eeuo pipefail

# Owner-host acceptance runner for an applied hyperpatch.
# P03 mode deliberately exercises the real local lifecycle.
# P04a mode is a deterministic/read-only acceptance profile for the frozen
# re-forensics/ontology foundation and does not repeat the network canary.

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd -P)"
cd "${PROJECT_ROOT}"

HYPERPATCH="p03"
PROFILE="default"
CANARY_SECONDS=2
RECOVER_ROOT=""
HOST_SETUP=1

usage() {
  cat <<'USAGE'
Использование:
  bash meta_tools/hyperpatch_acceptance.sh
  bash meta_tools/hyperpatch_acceptance.sh --p03
  bash meta_tools/hyperpatch_acceptance.sh --p04a
  bash meta_tools/hyperpatch_acceptance.sh --profile default
  bash meta_tools/hyperpatch_acceptance.sh --canary-seconds 3
  bash meta_tools/hyperpatch_acceptance.sh --p03 --recover-root /path/to/previous/UTS/project
  bash meta_tools/hyperpatch_acceptance.sh --p03 --no-host-setup

Смысл PASS для --p03:
  - P03 generation/inventory + focused regression прошли;
  - GUI Python dependency (PyQt6) доступна;
  - native nfqws2 собран штатным staged build path;
  - strategy parser preflight прошёл на реальном binary;
  - bounded root executor совпадает с source проекта;
  - stale legacy v0.4 nft table либо отсутствует, либо строго распознана и авторизована для атомарной миграции;
  - реальный default start применил owned nft/NFQUEUE rules и поднял nfqws2;
  - session остаётся running после canary window;
  - default stop остановил session и reverted owned nft rules.

Опциональный --recover-root сначала выполняет exact-identity stop/revert только для явно указанного старого workspace.
Если путь отсутствует (например, UTS остался на другой машине), recovery помечается SKIP и acceptance продолжается.
По умолчанию host setup включён: на Arch-family скрипт может установить недостающий python-pyqt6/build deps
и missing/mismatch project-owned bounded root-helper, после чего всегда повторно проверяет provenance.
--no-host-setup запрещает автоматическую установку host-local prerequisites и превращает их отсутствие в FAIL.
Скрипт реально меняет локальный nftables/NFQUEUE state на время canary.
При ошибке после попытки start выполняется best-effort confirmed stop/revert.
PASS означает runnable readiness текущего P03 hyperpatch на этом owner-host.
В конце автоматически создаётся ZIP с step logs и runtime state snapshot.
PASS НЕ доказывает эффективность конкретной DPI/ISP strategy на внешнем сайте.

Смысл PASS для --p04a:
  - post-P03f product baseline синхронизирован как v0.7/P04a;
  - frozen REP/CLI/S-INSTALL evidence совпадает с fixture;
  - P03 generation identity сохранена;
  - structural gate и полный pytest regression проходят;
  - никаких nft/NFQUEUE/network/root mutations не выполняется.
USAGE
}

while (($#)); do
  case "$1" in
    --p03)
      HYPERPATCH="p03"
      shift
      ;;
    --p04a)
      HYPERPATCH="p04a"
      shift
      ;;
    --profile)
      PROFILE="${2:-}"
      [[ -n "${PROFILE}" ]] || { echo "--profile требует значение" >&2; exit 2; }
      shift 2
      ;;
    --canary-seconds)
      CANARY_SECONDS="${2:-}"
      [[ "${CANARY_SECONDS}" =~ ^[0-9]+$ ]] || { echo "--canary-seconds должен быть целым >= 0" >&2; exit 2; }
      shift 2
      ;;
    --recover-root)
      RECOVER_ROOT="${2:-}"
      [[ -n "${RECOVER_ROOT}" ]] || { echo "--recover-root требует путь" >&2; exit 2; }
      shift 2
      ;;
    --no-host-setup)
      HOST_SETUP=0
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Неизвестный аргумент: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ "${HYPERPATCH}" != "p03" && "${HYPERPATCH}" != "p04a" ]]; then
  echo "Поддерживаются P03 и P04a acceptance profiles." >&2
  exit 2
fi
if [[ "${HYPERPATCH}" == "p04a" && -n "${RECOVER_ROOT}" ]]; then
  echo "--recover-root относится только к P03 owner-host lifecycle acceptance." >&2
  exit 2
fi
if [[ "$(id -u)" -eq 0 ]]; then
  echo "Acceptance runner нельзя запускать целиком через sudo/root. Запусти от owner-пользователя; bounded helper сам запросит sudo только там, где это нужно." >&2
  exit 2
fi
if [[ ! -f run.sh || ! -f pyproject.toml || ! -d gui || ! -d tests ]]; then
  echo "${PROJECT_ROOT} не похож на корень z2flingui project." >&2
  exit 2
fi

# shellcheck source=python_runtime.sh
source "${SCRIPT_DIR}/python_runtime.sh"

is_arch_family() {
  command -v pacman >/dev/null 2>&1
}

pick_acceptance_python() {
  zap2_pick_python "${PROJECT_ROOT}" PyQt6
}

ensure_gui_python() {
  local selected=""
  if selected="$(pick_acceptance_python 2>/dev/null)"; then
    PYTHON_BIN="${selected}"
    return 0
  fi
  if (( HOST_SETUP != 0 )) && is_arch_family; then
    printf '%s\n' '[HOST-SETUP] Python>=3.10 + PyQt6 не найдены в project/system candidates; устанавливаю Arch package python-pyqt6...' >&2
    sudo pacman -S --needed --noconfirm python python-pyqt6 || return 1
    selected="$(pick_acceptance_python)" || return 1
    PYTHON_BIN="${selected}"
    return 0
  fi
  return 1
}

PYTHON_BIN=""
if [[ "${HYPERPATCH}" == "p03" ]]; then
  if ! ensure_gui_python; then
    cat >&2 <<'ERR'
Не найден совместимый Python >= 3.10 с PyQt6.
Arch/Manjaro/EndeavourOS: sudo pacman -S --needed python python-pyqt6
Или укажи ZAP2_PYTHON=/path/to/python. Для автоматической host-подготовки не используй --no-host-setup.
ERR
    exit 2
  fi
else
  if ! PYTHON_BIN="$(zap2_pick_python "${PROJECT_ROOT}" pytest)"; then
    echo "Не найден совместимый Python >= 3.10 с pytest для P04a deterministic acceptance." >&2
    exit 2
  fi
  HOST_SETUP=0
fi

READINESS_MARKER="READY_FOR_USE_WITHIN_P03"
ACCEPTANCE_LABEL="P03 owner-host hyperpatch acceptance"
if [[ "${HYPERPATCH}" == "p04a" ]]; then
  READINESS_MARKER="READY_FOR_USE_WITHIN_P04A"
  ACCEPTANCE_LABEL="P04a deterministic hyperpatch acceptance"
fi

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOG_DIR="${PROJECT_ROOT}/.zap2/runtime/acceptance/${HYPERPATCH}-${STAMP}"
EVIDENCE_ARCHIVE="${LOG_DIR}.zip"
mkdir -p "${LOG_DIR}"
SUMMARY_FILE="${LOG_DIR}/summary.txt"
STEP_INDEX=0
LAST_OUTPUT_FILE=""
RUNTIME_CLEANUP_NEEDED=0
FINAL_PASS=0

say() {
  printf '%s\n' "$*" | tee -a "${SUMMARY_FILE}"
}

slugify() {
  printf '%s' "$1" | tr '[:upper:] ' '[:lower:]_' | tr -cd 'a-z0-9._-'
}

run_step() {
  local label="$1"
  shift
  STEP_INDEX=$((STEP_INDEX + 1))
  local slug
  slug="$(slugify "${label}")"
  local out="${LOG_DIR}/$(printf '%02d' "${STEP_INDEX}")-${slug}.log"
  say ""
  say "[RUN ${STEP_INDEX}] ${label}"
  printf '[CMD] ' | tee -a "${SUMMARY_FILE}"
  printf '%q ' "$@" | tee -a "${SUMMARY_FILE}"
  printf '\n' | tee -a "${SUMMARY_FILE}"
  set +e
  "$@" 2>&1 | tee "${out}"
  local rc=${PIPESTATUS[0]}
  set -e
  LAST_OUTPUT_FILE="${out}"
  if (( rc != 0 )); then
    say "[FAIL ${STEP_INDEX}] ${label}: rc=${rc}; log=${out}"
    return "${rc}"
  fi
  say "[PASS ${STEP_INDEX}] ${label}"
}

require_last() {
  local pattern="$1"
  local description="$2"
  if ! grep -Eq -- "${pattern}" "${LAST_OUTPUT_FILE}"; then
    say "[FAIL] ${description}; pattern=${pattern}; log=${LAST_OUTPUT_FILE}"
    return 1
  fi
}

field_from_last() {
  local key="$1"
  awk -v prefix="${key}" 'index($0,prefix)==1 {sub(prefix,"",$0); sub(/^[[:space:]]+/,"",$0); print; exit}' "${LAST_OUTPUT_FILE}"
}

collect_runtime_evidence() {
  local snapshot_dir="${LOG_DIR}/runtime-snapshot"
  mkdir -p "${snapshot_dir}"
  local candidates=(
    ".zap2/runtime/sessions/${PROFILE}.session.json"
    ".zap2/runtime/sessions/${PROFILE}.default-workflow.json"
    ".zap2/runtime/core-build-receipt.json"
    ".zap2/runtime/logs/${PROFILE}.runtime.jsonl"
  )
  local rel
  for rel in "${candidates[@]}"; do
    if [[ -f "${PROJECT_ROOT}/${rel}" ]]; then
      cp -- "${PROJECT_ROOT}/${rel}" "${snapshot_dir}/$(basename -- "${rel}")" || true
    fi
  done
}

pack_evidence() {
  collect_runtime_evidence
  set +e
  env LOG_DIR="${LOG_DIR}" EVIDENCE_ARCHIVE="${EVIDENCE_ARCHIVE}" "${PYTHON_BIN}" - <<'PYZIP'
import os
from pathlib import Path
import zipfile
root = Path(os.environ["LOG_DIR"])
out = Path(os.environ["EVIDENCE_ARCHIVE"])
with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
    for path in sorted(root.rglob("*")):
        if path.is_file():
            zf.write(path, path.relative_to(root.parent))
print(out)
PYZIP
  local rc=$?
  set -e
  if (( rc != 0 )); then
    say "[EVIDENCE-WARN] не удалось упаковать ${EVIDENCE_ARCHIVE}"
    return "${rc}"
  fi
  return 0
}

best_effort_stop() {
  local stop_plan_id="runtime-${PROFILE}-manual-local-default-stop-workflow-plan"
  say "[CLEANUP] Пытаюсь штатно остановить session и revert owned nft rules..."
  set +e
  env ZAP2_PYTHON="${PYTHON_BIN}" bash ./run.sh --cli --profile "${PROFILE}" --default-stop-plan
  local rc_plan=$?
  local rc_confirm=1
  local rc_stop=1
  if (( rc_plan == 0 )); then
    env ZAP2_PYTHON="${PYTHON_BIN}" bash ./run.sh --cli --profile "${PROFILE}" --runtime-confirm "${stop_plan_id}"
    rc_confirm=$?
  fi
  if (( rc_plan == 0 && rc_confirm == 0 )); then
    env ZAP2_PYTHON="${PYTHON_BIN}" bash ./run.sh --cli --profile "${PROFILE}" --default-stop --confirm "${stop_plan_id}"
    rc_stop=$?
  fi
  set -e
  if (( rc_plan == 0 && rc_confirm == 0 && rc_stop == 0 )); then
    say "[CLEANUP] stop/revert завершён."
    return 0
  fi
  say "[CLEANUP-FAIL] plan=${rc_plan} confirm=${rc_confirm} stop=${rc_stop}. Проверь --default-status и owned nft table вручную."
  return 1
}

on_exit() {
  local rc=$?
  trap - EXIT INT TERM
  local cleanup_rc=0
  if (( RUNTIME_CLEANUP_NEEDED != 0 )); then
    best_effort_stop || cleanup_rc=$?
  fi
  local evidence_rc=0
  pack_evidence || evidence_rc=$?
  if (( FINAL_PASS != 0 && rc == 0 && cleanup_rc == 0 )); then
    say ""
    say "HYPERPATCH ACCEPTANCE: PASS"
    say "readiness: ${READINESS_MARKER}"
    say "evidence: ${LOG_DIR}"
    if (( evidence_rc == 0 )); then say "evidence archive: ${EVIDENCE_ARCHIVE}"; fi
    exit 0
  fi
  if (( rc == 0 )); then rc=1; fi
  if (( cleanup_rc != 0 )); then rc=1; fi
  say ""
  say "HYPERPATCH ACCEPTANCE: FAIL"
  say "evidence: ${LOG_DIR}"
  if (( evidence_rc == 0 )); then say "evidence archive: ${EVIDENCE_ARCHIVE}"; fi
  exit "${rc}"
}
trap on_exit EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

say "${ACCEPTANCE_LABEL}"
say "project: ${PROJECT_ROOT}"
say "profile: ${PROFILE}"
say "python: ${PYTHON_BIN}"
say "host setup: $([[ ${HOST_SETUP} -eq 1 ]] && echo enabled || echo disabled)"
say "canary seconds: ${CANARY_SECONDS}"
say "evidence dir: ${LOG_DIR}"
run_step "Host portability fingerprint" "${PYTHON_BIN}" -c 'import os,platform,sys,pathlib; print("python executable:",sys.executable); print("python version:",platform.python_version()); print("kernel:",platform.release()); p=pathlib.Path("/etc/os-release"); print(p.read_text(errors="replace") if p.exists() else "os-release: unavailable")'

if [[ "${HYPERPATCH}" == "p04a" ]]; then
  run_step "P04a frozen re-forensics" env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="${PROJECT_ROOT}/gui${PYTHONPATH:+:${PYTHONPATH}}" "${PYTHON_BIN}" tools/gui_checks/check_p04a_re_forensics.py
  require_last '^P04a re-forensics: PASS$' "P04a frozen decision evidence не совпадает"

  run_step "P03 generation identity preserved" env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="${PROJECT_ROOT}/gui${PYTHONPATH:+:${PYTHONPATH}}" "${PYTHON_BIN}" tools/gui_checks/check_p03_core_generation.py
  require_last '^P03 core generation: PASS$' "P04a не должен ломать принятую P03 generation identity"

  run_step "Project tree structural gate" "${PYTHON_BIN}" tools/gui_checks/check_project_tree.py

  run_step "Full deterministic regression" env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="${PROJECT_ROOT}/gui${PYTHONPATH:+:${PYTHONPATH}}" "${PYTHON_BIN}" tools/gui_checks/check_p04a_regression.py
  require_last '^P04a regression: PASS \(.*\)$' "P04a full regression не PASS"

  FINAL_PASS=1
  exit 0
fi

if [[ -n "${RECOVER_ROOT}" ]]; then
  say "recover root: ${RECOVER_ROOT}"
  if [[ ! -e "${RECOVER_ROOT}" ]]; then
    say "[SKIP] Recover previous workspace runtime: путь отсутствует на этом host; recovery host-local и не применим после переезда машины."
  else
    run_step "Recover previous workspace runtime" env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="${PROJECT_ROOT}/gui${PYTHONPATH:+:${PYTHONPATH}}" "${PYTHON_BIN}" meta_tools/recover_runtime_workspace.py --root "${RECOVER_ROOT}" --profile "${PROFILE}"
    require_last '^PREVIOUS WORKSPACE RECOVERY: PASS$' "previous workspace recovery не PASS"
  fi
fi

# 1. Deterministic hyperpatch evidence.
run_step "P03 generation identity" env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="${PROJECT_ROOT}/gui${PYTHONPATH:+:${PYTHONPATH}}" "${PYTHON_BIN}" tools/gui_checks/check_p03_core_generation.py
require_last '^P03 core generation: PASS$' "P03 generation contract не PASS"

run_step "Core inventory exactness" "${PYTHON_BIN}" tools/gui_checks/inventory_core.py --check
require_last 'Инвентаризация ядра и build map актуальны' "core inventory не подтверждён"

run_step "P03 regression" env ZAP2_UTS_PYTHON="${PYTHON_BIN}" bash meta_tools/uts_prepare.sh --p03

run_step "Project tree structural gate" "${PYTHON_BIN}" tools/gui_checks/check_project_tree.py

# GUI readiness here means Python GUI runtime can at least be imported on this host.
run_step "GUI Python/PyQt6 readiness" "${PYTHON_BIN}" -c 'import sys; import PyQt6; print("Python executable:", sys.executable); print("Python version:", sys.version.split()[0]); print("PyQt6 import: PASS")' 
require_last '^PyQt6 import: PASS$' "PyQt6 недоступен выбранному Python"

# 2. Native generation build.
run_step "Native build dependency preflight" env ZAP2_PYTHON="${PYTHON_BIN}" bash ./run.sh --cli --profile "${PROFILE}" --default-build-deps
if ! grep -Eq '^status: ok$' "${LAST_OUTPUT_FILE}"; then
  if (( HOST_SETUP != 0 )) && is_arch_family; then
    run_step "Install Arch native build dependencies" sudo pacman -S --needed --noconfirm base-devel pkgconf zlib libnetfilter_queue libnfnetlink libmnl luajit
    run_step "Native build dependency preflight after setup" env ZAP2_PYTHON="${PYTHON_BIN}" bash ./run.sh --cli --profile "${PROFILE}" --default-build-deps
  fi
fi
require_last '^status: ok$' "native build dependencies не готовы"

run_step "Default build plan" env ZAP2_PYTHON="${PYTHON_BIN}" bash ./run.sh --cli --profile "${PROFILE}" --default-build-plan
BUILD_PLAN_ID="$(field_from_last 'plan id:')"
[[ -n "${BUILD_PLAN_ID}" ]] || { say "[FAIL] build plan id не найден"; exit 1; }

run_step "Confirm default build" env ZAP2_PYTHON="${PYTHON_BIN}" bash ./run.sh --cli --profile "${PROFILE}" --runtime-confirm "${BUILD_PLAN_ID}"
run_step "Native staged nfqws2 build" env ZAP2_PYTHON="${PYTHON_BIN}" bash ./run.sh --cli --profile "${PROFILE}" --default-build --confirm "${BUILD_PLAN_ID}"
require_last '^Default build: built$' "native build не завершился state=built"
require_last 'exists=yes; executable=yes' "native nfqws2 artifact не executable"

run_step "Generation build receipt v2" env PROJECT_ROOT="${PROJECT_ROOT}" "${PYTHON_BIN}" -c 'import json,os,pathlib; p=pathlib.Path(os.environ["PROJECT_ROOT"])/".zap2/runtime/core-build-receipt.json"; d=json.loads(p.read_text()); assert d.get("marker")=="zap2-core-generation-build-receipt-v2" and d.get("schemaVersion")==2; a=d.get("artifacts") or []; assert a and a[0].get("sha256"); print("core build receipt v2: PASS")'

run_step "Native strategy parser preflight" env ZAP2_PYTHON="${PYTHON_BIN}" bash ./run.sh --cli --profile "${PROFILE}" --strategy-parser-preflight
require_last '^exit code: 0$' "nfqws2 dry-run вернул ненулевой exit"
require_last '^verdict: PASS$' "strategy parser preflight не PASS"
require_last '^nfqueue qnum: [0-9]+$' "parser preflight не получил qnum"

# 3. Privilege boundary readiness.
run_step "Bounded privileged executor provenance" env ZAP2_PYTHON="${PYTHON_BIN}" bash ./run.sh --cli --profile "${PROFILE}" --privileged-executor-status
HELPER_STATE="$(awk -F': ' '/^P02 privileged executor:/ {print $2; exit}' "${LAST_OUTPUT_FILE}")"
if [[ "${HELPER_STATE}" != "ready" ]]; then
  if (( HOST_SETUP != 0 )) && [[ "${HELPER_STATE}" == "missing" || "${HELPER_STATE}" == "mismatch" ]]; then
    HELPER_SOURCE="${PROJECT_ROOT}/tools/privileged/zap2-runtime-executor"
    HELPER_TARGET="/usr/local/libexec/zap2-runtime-executor"
    [[ -f "${HELPER_SOURCE}" && ! -L "${HELPER_SOURCE}" ]] || { say "[FAIL] project privileged helper source invalid: ${HELPER_SOURCE}"; exit 1; }
    run_step "Install/update bounded privileged executor" sudo install -D -o root -g root -m 0755 -- "${HELPER_SOURCE}" "${HELPER_TARGET}"
    run_step "Bounded privileged executor provenance after setup" env ZAP2_PYTHON="${PYTHON_BIN}" bash ./run.sh --cli --profile "${PROFILE}" --privileged-executor-status
    HELPER_STATE="$(awk -F': ' '/^P02 privileged executor:/ {print $2; exit}' "${LAST_OUTPUT_FILE}")"
  fi
fi
require_last '^P02 privileged executor: ready$' "bounded privileged executor не ready; untrusted/unknown helper не исправляется автоматически"
require_last '^root imports workspace Python: no$' "root helper не должен импортировать workspace Python"
INSTALLED_SHA="$(awk '/^installed sha256:/ {print $3; exit}' "${LAST_OUTPUT_FILE}")"
PROJECT_SHA="$(awk '/^project sha256:/ {print $3; exit}' "${LAST_OUTPUT_FILE}")"
if [[ -z "${INSTALLED_SHA}" || "${INSTALLED_SHA}" != "${PROJECT_SHA}" ]]; then
  say "[FAIL] installed/project privileged helper SHA mismatch"
  exit 1
fi

# P03e: safely converge a stale pre-P02/v0.4 generic nft table.  The guard
# only authorizes migration when the exact historical Zap2 fingerprint is
# observed and none of its queue numbers has a live NFQUEUE listener.  The
# table is not deleted here: deletion remains part of the normal confirmed
# atomic owner-rules apply transaction.
run_step "Legacy v0.4 nft collision guard" env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="${PROJECT_ROOT}/gui${PYTHONPATH:+:${PYTHONPATH}}" "${PYTHON_BIN}" meta_tools/prepare_legacy_v04_migration.py --root "${PROJECT_ROOT}" --profile "${PROFILE}"
require_last '^Legacy v0\.4 nft migration: (absent|authorized)$' "legacy v0.4 nft state не удалось безопасно классифицировать/авторизовать"

# Refuse to hijack an already-running default workflow.
run_step "Initial default runtime status" env ZAP2_PYTHON="${PYTHON_BIN}" bash ./run.sh --cli --profile "${PROFILE}" --default-status
if grep -Eq '^Default workflow status: started$|^session status: running$' "${LAST_OUTPUT_FILE}"; then
  say "[FAIL] default runtime уже running; acceptance не будет переиспользовать живую session"
  exit 1
fi

# 4. Real owner-host canary. This temporarily mutates owned nft/NFQUEUE state.
run_step "Default start plan" env ZAP2_PYTHON="${PYTHON_BIN}" bash ./run.sh --cli --profile "${PROFILE}" --default-start-plan
START_PLAN_ID="$(field_from_last 'plan id:')"
[[ -n "${START_PLAN_ID}" ]] || { say "[FAIL] start plan id не найден"; exit 1; }
run_step "Confirm default start" env ZAP2_PYTHON="${PYTHON_BIN}" bash ./run.sh --cli --profile "${PROFILE}" --runtime-confirm "${START_PLAN_ID}"

RUNTIME_CLEANUP_NEEDED=1
run_step "Real nft/NFQUEUE start canary" env ZAP2_PYTHON="${PYTHON_BIN}" bash ./run.sh --cli --profile "${PROFILE}" --default-start --confirm "${START_PLAN_ID}"
require_last '^Default workflow start: started$' "default start не достиг state=started"
require_last '^session result: running$' "nfqws2 session не запущена"
require_last '^owner rules result: applied$' "owned nft rules не applied"

if (( CANARY_SECONDS > 0 )); then
  say "[WAIT] ${CANARY_SECONDS}s session health canary"
  sleep "${CANARY_SECONDS}"
fi

run_step "Default status while running" env ZAP2_PYTHON="${PYTHON_BIN}" bash ./run.sh --cli --profile "${PROFILE}" --default-status
require_last '^Default workflow status: started$' "workflow не остаётся started после canary window"
require_last '^session status: running$' "session не остаётся running после canary window"

run_step "Runtime session health" env ZAP2_PYTHON="${PYTHON_BIN}" bash ./run.sh --cli --profile "${PROFILE}" --runtime-session-status
require_last '^Runtime session status: running$' "runtime session health не running"

run_step "Runtime nft/NFQUEUE state" env ZAP2_PYTHON="${PYTHON_BIN}" bash ./run.sh --cli --profile "${PROFILE}" --runtime-nft-state
require_last '^owner-rules state: applied$' "owner-rules state не applied"
require_last '^nfqws2 session state: running$' "nft snapshot не видит running nfqws2"

run_step "Runtime logs snapshot" env ZAP2_PYTHON="${PYTHON_BIN}" bash ./run.sh --cli --profile "${PROFILE}" --runtime-logs

# 5. Normal lifecycle cleanup is part of acceptance, not an afterthought.
run_step "Default stop plan" env ZAP2_PYTHON="${PYTHON_BIN}" bash ./run.sh --cli --profile "${PROFILE}" --default-stop-plan
STOP_PLAN_ID="$(field_from_last 'plan id:')"
[[ -n "${STOP_PLAN_ID}" ]] || { say "[FAIL] stop plan id не найден"; exit 1; }
run_step "Confirm default stop" env ZAP2_PYTHON="${PYTHON_BIN}" bash ./run.sh --cli --profile "${PROFILE}" --runtime-confirm "${STOP_PLAN_ID}"
run_step "Default stop and nft revert" env ZAP2_PYTHON="${PYTHON_BIN}" bash ./run.sh --cli --profile "${PROFILE}" --default-stop --confirm "${STOP_PLAN_ID}"
require_last '^Default workflow stop: stopped$' "default stop не достиг state=stopped"
require_last '^owner rules result: reverted$' "owned nft rules не reverted"
RUNTIME_CLEANUP_NEEDED=0

run_step "Post-stop default status" env ZAP2_PYTHON="${PYTHON_BIN}" bash ./run.sh --cli --profile "${PROFILE}" --default-status
require_last '^Default workflow status: stopped$' "workflow state после cleanup не stopped"
require_last '^session status: stopped$' "session state после cleanup не stopped"

run_step "Post-stop nft/NFQUEUE state" env ZAP2_PYTHON="${PYTHON_BIN}" bash ./run.sh --cli --profile "${PROFILE}" --runtime-nft-state
require_last '^owner-rules state: reverted$' "owner-rules state после cleanup не reverted"
require_last '^nfqws2 session state: stopped$' "nfqws2 state после cleanup не stopped"

FINAL_PASS=1
