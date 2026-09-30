#!/usr/bin/env bash
set -Eeuo pipefail
ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
source "${ROOT_DIR}/meta_tools/python_runtime.sh"
PYTHON_BIN="$(zap2_pick_python "${ROOT_DIR}")"
VERSION="$("${PYTHON_BIN}" -c 'import re,sys,pathlib; print(re.search(r"^version\s*=\s*\"([^\"]+)\"",pathlib.Path(sys.argv[1]).read_text(),re.M).group(1))' "${ROOT_DIR}/pyproject.toml")"
OUTPUT_DIR="${ROOT_DIR}/dist/arch/${VERSION}"
INSTALL=0
while (( $# )); do
  case "$1" in
    --out) [[ $# -ge 2 ]] || { echo "--out требует каталог" >&2; exit 2; }; OUTPUT_DIR="$2"; shift 2 ;;
    --install) INSTALL=1; shift ;;
    --help) echo "bash meta_tools/build_local_package.sh [--out DIR] [--install]"; exit 0 ;;
    *) echo "Неизвестный аргумент: $1" >&2; exit 2 ;;
  esac
done
if (( INSTALL )); then
  [[ "$(id -u)" != 0 ]] || { echo "makepkg запускают обычным пользователем" >&2; exit 2; }
  command -v makepkg >/dev/null || { echo "Нужен makepkg из base-devel" >&2; exit 2; }
fi
mkdir -p -- "${OUTPUT_DIR}"
OUTPUT_DIR="$(cd -- "${OUTPUT_DIR}" && pwd -P)"
"${PYTHON_BIN}" "${ROOT_DIR}/packaging/build_release.py" --root "${ROOT_DIR}" --out "${OUTPUT_DIR}/zap2gui-linux-${VERSION}.tar.gz" --pkgbuild "${OUTPUT_DIR}/PKGBUILD"
echo "Archive и PKGBUILD созданы в: ${OUTPUT_DIR}"
if (( INSTALL )); then
  cd -- "${OUTPUT_DIR}"
  makepkg -si
else
  echo "Для сборки и установки пакета перейдите в этот каталог и выполните makepkg -si."
fi
