#!/bin/sh
# Read-only target DNS gate, executed in the same privileged context as blockcheck2.
# Do not replace an unresolved hostname with a guessed address: upstream uses mdig
# too, and running a DPI scan with no endpoint address would give false evidence.
set -u

: "${ZAPRET_BASE:?ZAPRET_BASE is required}"
: "${ZAP2_BLOCKCHECK_SCRIPT:?ZAP2_BLOCKCHECK_SCRIPT is required}"
: "${ZAP2_TARGET_HOSTS:?ZAP2_TARGET_HOSTS is required}"

MDIG=${MDIG:-"${ZAPRET_BASE}/mdig/mdig"}
IPVS=${IPVS:-4}

# Raw candidate log receives stderr; tournament UI only presents stable codes.
# mdig --verbose reports getaddrinfo EAI_* errors without requiring a second
# DNS service or writing addresses to a persistent file.
if [ ! -x "$MDIG" ]; then
    echo "[zap2] target DNS preflight FAILED: mdig executable missing or not executable" >&2
    echo "[zap2] DNS gate detail: mdig-missing; build/rebuild mdig in the active workspace" >&2
    echo "[zap2] Blockcheck was not started; firewall was not touched." >&2
    exit 7
fi

check_family()
{
    family=$1
    for host in ${ZAP2_TARGET_HOSTS}; do
        # mdig may exit zero even if no record was returned. It uses getaddrinfo
        # with AF_INET/AF_INET6 and SOCK_DGRAM; keep the exact upstream resolver.
        answer=$(printf '%s\n' "$host" | "$MDIG" --family="$family" --verbose | tr -d '\r' | sed '/^[[:space:]]*$/d')
        if [ -z "$answer" ]; then
            echo "[zap2] target DNS preflight FAILED: $host has no IPv$family answer from mdig" >&2
            # Cross-check the system NSS resolver in the same privilege context.
            # This is diagnostic only: getent answers must not be substituted
            # for the IP list used by blockcheck2's own mdig_cache.
            if command -v getent >/dev/null 2>&1; then
                if getent "ahostsv$family" "$host" >/dev/null 2>&1; then
                    echo "[zap2] DNS gate detail: mdig-nss-mismatch; getent resolved this family" >&2
                else
                    echo "[zap2] DNS gate detail: resolver-unavailable; getent also failed this family" >&2
                fi
            else
                echo "[zap2] DNS gate detail: resolver-unavailable; getent is not installed" >&2
            fi
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
        echo "[zap2] Blockcheck was not started; firewall was not touched." >&2
        exit 2
        ;;
esac

echo "[zap2] target DNS preflight OK: ${ZAP2_TARGET_HOSTS} (IPVS=${IPVS})"
exec /bin/sh "$ZAP2_BLOCKCHECK_SCRIPT"
