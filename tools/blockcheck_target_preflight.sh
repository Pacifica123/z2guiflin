#!/bin/sh
# Read-only target-specific DNS gate for GUI/CLI Blockcheck.
# It runs inside the same sudo/QProcess context as upstream blockcheck2.sh and
# deliberately performs no firewall or service mutation. General DNS/hijack
# diagnostics remain upstream's responsibility; this guard only verifies that
# each selected target can produce an address for every requested IP family.
set -u

: "${ZAPRET_BASE:?ZAPRET_BASE is required}"
: "${ZAP2_BLOCKCHECK_SCRIPT:?ZAP2_BLOCKCHECK_SCRIPT is required}"
: "${ZAP2_TARGET_HOSTS:?ZAP2_TARGET_HOSTS is required}"

MDIG=${MDIG:-"${ZAPRET_BASE}/mdig/mdig"}
IPVS=${IPVS:-4}

check_family()
{
    family=$1
    for host in ${ZAP2_TARGET_HOSTS}; do
        # mdig can return success with an empty answer. Only non-empty stdout is
        # accepted; stderr is intentionally suppressed and replaced by one
        # stable user-facing diagnostic below.
        answer=$(printf '%s\n' "$host" | "$MDIG" --family="$family" 2>/dev/null | tr -d '\r' | sed '/^[[:space:]]*$/d')
        if [ -z "$answer" ]; then
            echo "[zap2] target DNS preflight FAILED: $host has no IPv$family answer from mdig" >&2
            echo "[zap2] Blockcheck was not started; firewall was not touched. Check system DNS/DoH differences and retry." >&2
            exit 6
        fi
    done
}

case "$IPVS" in
    4) check_family 4 ;;
    6) check_family 6 ;;
    46|64)
        check_family 4
        check_family 6
        ;;
    *)
        echo "[zap2] target DNS preflight FAILED: unsupported IPVS=$IPVS" >&2
        exit 2
        ;;
esac

echo "[zap2] target DNS preflight OK: ${ZAP2_TARGET_HOSTS} (IPVS=${IPVS})"
exec /bin/sh "$ZAP2_BLOCKCHECK_SCRIPT"
