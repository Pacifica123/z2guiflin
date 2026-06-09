# v0.4-alpha Stage 7l.1 — runtime args-file quoting retry

Fixes the failed Stage 7l devctl check and preserves the original runtime startup fix for `community-discord-syndata-edge-flow-v2`.

Changes:

- shell-quote every token written to `.zap2/runtime/sessions/*.nfqws2.args`;
- reject newline/NUL in `nfqws2` runtime args;
- avoid stale root-owned `/tmp/zap2-runtime-inputs` check failures by using a uid-scoped default public runtime input base;
- keep explicit `ZAP2_PUBLIC_RUNTIME_INPUTS_DIR` behavior unchanged for tests and owner overrides.

This patch does not claim Discord success. It only allows the community v2 strategy to start cleanly so the SYN-SENT observation loop can continue.
