# v2rayNG reference notes for the Discord tunnel lane

The uploaded `v2rayNG-2dust.zip` was inspected as a reference source for the
future SOCKS/VLESS tunnel lane.  This note records concepts, not copied code.

## License and portability boundary

The project contains a GPL-3.0 license file and is an Android/Kotlin codebase.
Zap2GUIfLin should not copy implementation code into the current Python/Linux
project unless the repository licensing strategy is deliberately changed.  The
safe Stage 7p0 posture is: use the project as a reference for concepts and write
native Zap2 code independently.

## Reference files inspected

```text
V2rayNG/app/src/main/java/com/v2ray/ang/fmt/VlessFmt.kt
V2rayNG/app/src/main/java/com/v2ray/ang/fmt/FmtBase.kt
V2rayNG/app/src/main/java/com/v2ray/ang/AppConfig.kt
V2rayNG/app/src/main/assets/v2ray_config.json
V2rayNG/app/src/main/assets/v2ray_config_with_tun.json
V2rayNG/app/src/main/java/com/v2ray/ang/core/CoreOutboundBuilder.kt
V2rayNG/app/src/main/java/com/v2ray/ang/service/CoreProxyOnlyService.kt
V2rayNG/app/src/main/java/com/v2ray/ang/service/CoreVpnService.kt
V2rayNG/app/src/main/java/com/v2ray/ang/ui/PerAppProxyActivity.kt
```

## Useful ideas for Zap2GUIfLin

- Parse share-link URIs into an internal profile object first; generate a core
  config later.
- Keep local proxy defaults explicit; v2rayNG uses a local SOCKS concept around
  loopback and a common default port such as `10808`.
- A local SOCKS inbound can enable UDP, but Zap2 should keep UDP off by default
  until a Discord voice/media phase needs it.
- Sniffing concepts for `http`, `tls`, and `quic` are relevant when generating
  a core config, but should be owner-visible in the generated JSON.
- Proxy-only service and VPN/TUN service should be separate modes.  Zap2 should
  implement SOCKS proxy-only first and leave TUN/TProxy for a later root-required
  lane.
- Per-app proxy is a product idea we want, but Android package selection does
  not translate directly to Linux desktop Discord.

## Ideas that should not be ported directly

- Android `VpnService` mechanics.
- Android activities/fragments and MMKV storage.
- Android package UID selection as-is.
- Any hard-coded mobile assumptions about app lifecycle.
- Any raw third-party configs, credentials, or copied Kotlin implementation.

## Zap2-specific adaptation

Zap2 should adapt the ideas this way:

```text
v2rayNG share profile     -> Zap2 tunnel connection profile
v2rayNG local SOCKS       -> Zap2 loopback SOCKS inbound
v2rayNG proxy-only mode   -> Zap2 external-core proxy-only runtime
v2rayNG VPN mode          -> future Zap2 TUN/TProxy research lane
v2rayNG per-app proxy     -> future Linux Discord launcher/routing mode
```

## Secret handling rule

The owner's sample URI is treated as a private runtime input.  The repository
must contain only redacted examples such as:

```text
vless://<uuid>@<server>:<port>?type=tcp&encryption=none#<remarks>
```

Raw UUIDs, endpoint addresses, and full share links belong in `.zap2/tunnel` at
runtime, not in docs or patch payloads.


## Stage 7p1 implementation use

The Stage 7p1-7p4 implementation keeps v2rayNG as a reference-only source.  The
actual Python code is native Zap2 code and does not copy Kotlin implementation.
The concrete ideas carried over are:

- parse share links into a local profile model instead of treating raw URIs as
  runtime args;
- create a loopback SOCKS inbound with sniffing hints;
- generate a core JSON config from profile data;
- keep the proxy-only lane separate from future VPN/TUN routing;
- treat process/session state as a managed service lifecycle with explicit stop.
