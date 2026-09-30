#!/usr/bin/env bash
# Manual clean-VM lifecycle recorder. System mutation requires this explicit mode.
set -euo pipefail
if [[ $# -ne 4 || "$1" != "--allow-system-install" ]]; then
  echo 'Usage: bash meta_tools/p06_vm_acceptance.sh --allow-system-install OLD_PACKAGE NEW_PACKAGE EVIDENCE_DIR' >&2
  echo 'Use two independently built Arch packages in a fresh disposable VM; no checkout required at runtime.' >&2
  exit 2
fi
[[ $(id -u) -ne 0 ]] || { echo 'Run as ordinary VM owner, not root.' >&2; exit 2; }
command -v pacman >/dev/null
OLD=$(realpath "$2");NEW=$(realpath "$3");OUT=$(realpath -m "$4")
[[ -f "$OLD" && -f "$NEW" && "$OLD" != "$NEW" && ! -e "$OUT" ]] || exit 2
old_version=$(pacman -Qp "$OLD" | awk '{print $2}')
new_version=$(pacman -Qp "$NEW" | awk '{print $2}')
[[ "$old_version" != "$new_version" ]] || { echo 'Same version reinstall cannot prove upgrade.' >&2; exit 2; }
if pacman -Q zap2gui-linux >/dev/null 2>&1; then echo 'Fresh VM must have no existing zap2gui-linux package.' >&2;exit 2;fi
mkdir -m 700 -p "$OUT"
# An isolated owner data directory permits explicit preservation checks.
export XDG_DATA_HOME="$OUT/user-data" XDG_CONFIG_HOME="$OUT/user-config"
unset PYTHONPATH ZAP2_RESOURCE_ROOT ZAP2_INSTALLED_ROOT ZAP2_PRIVILEGED_EXECUTOR
STATUS=FAIL
finish() {
  rc=$?
  printf '{"schemaVersion":1,"result":"%s","oldVersion":"%s","newVersion":"%s","exitCode":%s,"scope":"manual fresh Arch VM lifecycle; user attestations retained separately"}\n' "$STATUS" "$old_version" "$new_version" "$rc" > "$OUT/summary.json"
  echo "P06 VM lifecycle: $STATUS; evidence: $OUT"
}
trap finish EXIT
step() { local name=$1;shift;echo "[RUN] $name";"$@" > "$OUT/$name.log" 2>&1 || { cat "$OUT/$name.log";return 1; }; }
attest() {
  local name=$1;shift
  printf '%s\nType PASS only after observing all requested checks, otherwise FAIL: ' "$*"
  local answer;read -r answer
  printf '%s\n' "$answer" > "$OUT/$name.attestation"
  [[ "$answer" == PASS ]]
}
step install-old sudo pacman -U --noconfirm "$OLD"
cd "$OUT" # outside source checkout
step old-preflight zap2-gui --package-preflight
step old-status zap2-gui --action default.workflow.status
step old-plan zap2-gui --action default.workflow.plan.start
# GUI launch is part of the actual path; close it before proceeding.
step old-gui zap2-gui --gui
attest old-gui 'GUI launched through /usr/bin/zap2-gui. Inspect effects/privileges/help and About axes. It must not write /usr.'
# Use canonical GUI owner-confirmed build/start/stop and verify helper ready.
# We do not reuse the checkout-oriented P03 script, which requires tests/.
attest old-runtime 'Launch zap2-gui. Inspect build dependencies; build with owner confirmation, then owned default start/status/stop. Confirm helper is /usr/lib/zap2gui/zap2-runtime-executor, root-owned, non-writable; confirm stop/revert leaves no owned process/table. Record output in evidence before PASS.'
WS="$XDG_DATA_HOME/zap2gui/workspace"
cp "$WS/.zap2/installation/receipt.json" "$OUT/old-workspace-receipt.json"
printf 'p06-preserve-user-data\n' > "$WS/.zap2/p06-preservation-marker"
step upgrade sudo pacman -U --noconfirm "$NEW"
step new-preflight zap2-gui --package-preflight
step new-status zap2-gui --action default.workflow.status
cp "$WS/.zap2/installation/receipt.json" "$OUT/new-workspace-receipt.json"
step upgrade-receipt python - "$OUT" <<'PY'
import json,sys
from pathlib import Path
out=Path(sys.argv[1]);old=json.loads((out/'old-workspace-receipt.json').read_text());new=json.loads((out/'new-workspace-receipt.json').read_text())
assert new['releaseDigest']!=old['releaseDigest'] and new['previousReleaseDigest']==old['releaseDigest']
assert (out/'user-data/zap2gui/workspace/.zap2/p06-preservation-marker').read_text()=='p06-preserve-user-data\n'
assert (out/'user-data/zap2gui/backups'/('workspace-'+old['releaseDigest'][:16])).exists()
print('genuine release transition and preserved data: PASS')
PY
step new-gui zap2-gui --gui
attest new-runtime 'Through installed GUI verify helper hash/provenance after upgrade, rebuild if needed, owned start/status/stop, preset and tunnel diagnostics. Check UNKNOWN/NOT_RUN are truthful and no foreign cleanup occurs. Save diagnostic output separately before PASS.'
step new-about zap2-gui --about
step support zap2-gui --support-bundle "$OUT/support.zip"
attest support-redaction 'Inspect support.zip: useful typed evidence, no raw VLESS/config/logs/password/token/UUID/server. Stop/revert all owned runtime before uninstall.'
step uninstall sudo pacman -R --noconfirm zap2gui-linux
[[ ! -e /usr/bin/zap2-gui && ! -e /usr/lib/zap2gui/zap2-runtime-executor ]]
[[ -f "$WS/.zap2/installation/receipt.json" && -f "$WS/.zap2/p06-preservation-marker" ]]
attest uninstall 'User workspace, backups and settings retained; package-owned files removed; no owned runtime/table left. No foreign files changed.'
STATUS=PASS
