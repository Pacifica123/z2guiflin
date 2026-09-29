#!/usr/bin/env bash
# Shared Python runtime selector for z2guiflin owner-side tools.
# Explicit override -> project venv -> distro/system Python -> PATH fallback.
# The selector validates Python >= 3.10 and optional importable modules.

zap2_python_candidate_ok() {
  local candidate="$1"
  shift || true
  [[ -x "${candidate}" ]] || return 1
  "${candidate}" - "$@" <<'PY'
import importlib.util
import sys

if sys.version_info < (3, 10):
    raise SystemExit(1)
for module in sys.argv[1:]:
    if importlib.util.find_spec(module) is None:
        raise SystemExit(1)
raise SystemExit(0)
PY
}

zap2_resolve_python_command() {
  local value="$1"
  if [[ "${value}" == */* ]]; then
    [[ -x "${value}" ]] || return 1
    printf '%s\n' "${value}"
    return 0
  fi
  command -v -- "${value}" 2>/dev/null
}

zap2_pick_python() {
  local project_root="$1"
  shift || true
  local -a required_modules=("$@")
  local candidate resolved
  local -a candidates=()

  if [[ -n "${ZAP2_PYTHON:-}" ]]; then
    resolved="$(zap2_resolve_python_command "${ZAP2_PYTHON}")" || {
      printf 'ZAP2_PYTHON=%s не найден или не executable.\n' "${ZAP2_PYTHON}" >&2
      return 1
    }
    if zap2_python_candidate_ok "${resolved}" "${required_modules[@]}"; then
      printf '%s\n' "${resolved}"
      return 0
    fi
    printf 'ZAP2_PYTHON=%s не удовлетворяет Python>=3.10%s.\n' \
      "${resolved}" "${required_modules[*]:+ / modules: ${required_modules[*]}}" >&2
    return 1
  fi

  candidates+=("${project_root}/.venv/bin/python")
  # Arch-family package dependencies are installed for /usr/bin/python3. Prefer
  # the distro interpreter over pyenv/asdf shims in PATH when no project venv
  # or explicit override is selected.
  candidates+=("/usr/bin/python3" "/usr/bin/python")
  if command -v python3 >/dev/null 2>&1; then candidates+=("$(command -v python3)"); fi
  if command -v python >/dev/null 2>&1; then candidates+=("$(command -v python)"); fi

  local seen='|'
  for candidate in "${candidates[@]}"; do
    [[ -n "${candidate}" ]] || continue
    if [[ "${seen}" == *"|${candidate}|"* ]]; then continue; fi
    seen+="${candidate}|"
    if zap2_python_candidate_ok "${candidate}" "${required_modules[@]}"; then
      printf '%s\n' "${candidate}"
      return 0
    fi
  done
  return 1
}
