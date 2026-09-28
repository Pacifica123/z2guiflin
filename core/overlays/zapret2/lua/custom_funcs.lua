-- Zap2 project-local compatibility helpers for community Windows presets.
-- P03 generation: LOCAL_OVERLAY for zapret2 1.0.6 / LUA_COMPAT_VER=6.
--
-- The community preset that unblocked Discord on Windows uses
-- `hostfakesplit_multi:hosts=a,b`. The vendored bol-van zapret2 core ships
-- built-in `hostfakesplit`, but not this community helper. This shim keeps the
-- Linux runtime args parseable by mapping the multi helper to the first host in
-- the comma-separated list. It is intentionally conservative: the function does
-- not try to emulate WinDivert-only behavior and can be replaced by a fuller
-- upstream/community implementation later.

local function zap2_first_host(hosts)
    if not hosts then return nil end
    local first = tostring(hosts):match("^%s*([^,%s]+)")
    if first == "" then return nil end
    return first
end

function hostfakesplit_multi(ctx, desync)
    if not hostfakesplit then
        DLOG("hostfakesplit_multi: built-in hostfakesplit is unavailable")
        return
    end
    local previous_host = desync.arg.host
    local chosen_host = zap2_first_host(desync.arg.hosts) or zap2_first_host(desync.arg.host)
    if not chosen_host then
        DLOG("hostfakesplit_multi: no hosts= value; falling back to hostfakesplit unchanged")
        return hostfakesplit(ctx, desync)
    end
    desync.arg.host = chosen_host
    local verdict = hostfakesplit(ctx, desync)
    desync.arg.host = previous_host
    return verdict
end
