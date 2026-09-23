# P02 — owned lifecycle/state + privilege boundary

## Verdict

P02 сохраняет доказанные ownership/process lifecycle механизмы и убирает broad-root import
writable workspace. Каноническая цепочка стандартного runtime:

```text
Spec -> immutable Plan{hash,file-byte digests,owner,queue}
     -> owner confirmation
     -> Run{runId}
     -> finite privileged actions
     -> Evidence/receipts
     -> owner-state verdict
```

## Re-forensics after P01

Baseline HEAD: `d00f3e2`.

Подтверждённый P02 blocker до изменения:

```text
sudo -A env PYTHONPATH=<workspace>/gui ... python -m zap2_gui.app ...
```

После GUI confirmation writable Python source мог измениться до privileged import. Поэтому
listener/PID ownership был недостаточен: privilege effect не был привязан к immutable plan bytes.

## S-UPSTREAM shadow probe

Архив владельца: `zapret2-bol-van_originalcore_by2026sep23(1).zip`.
SHA-256 архива: `769df14fa4463fbe9744a2aab97e7f1bfe1a2f77a669981f4e6372d7b86d71a9`.

Shadow probe выполнялся без vendored switch. Текущий `core/zapret2` заканчивается changelog
`0.9.5.3` и использует `LUA_COMPAT_VER=5`; candidate заканчивается `1.0.6` и использует
`LUA_COMPAT_VER=6`. Это подтверждает P03 как отдельную semantic generation migration и
запрещает P02 цементировать parser/Lua assumptions старого core.

Raw tree counts (`current project core` против `candidate archive`) не являются import manifest
из-за project metadata/excluded CI/prebuilt artifacts: 250 и 253 files соответственно. Их нельзя
трактовать как прямой source diff; authoritative semantic migration остаётся P03.

## P02 boundary

Standard privileged effects доступны только через root-owned
`/usr/local/libexec/zap2-runtime-executor`:

- fixed finite action IDs: nft observe/check/execute и confirmed nfqws start;
- canonical request hash over stdin bytes;
- PlanHash/confirmation revalidated inside helper;
- installed helper hash must equal project helper source hash;
- no arbitrary env, shell, executable or writable project Python import;
- exact nfqws2/Lua/hostlist/blob bytes are digested into start plan;
- helper reads each source once, checks the digest, stages the same bytes into root-owned `/run/zap2`,
  then starts only the staged binary;
- nft batch is transported as bytes and checked against the confirmed plan rather than re-reading a
  mutable transaction path for authority.

## Lifecycle truth

Composite default workflow has one `runId`; child nft/session state records the same lineage.
Read-only `runtime_kernel_status` exposes one of:

`absent | owned-active | owned-stale | owned-partial | foreign-conflict | unknown | migration-required`.

Reconcile may mutate only proven owned state. Foreign/unknown resources have no auto-repair/delete
path.

Legacy session schema migration is explicit and receipted. Read-only status never performs it.
Newer schema is refused.

## Deferred/staged surfaces

- `service-apply`: plan-only in P02; no systemd privileged executor action yet.
- GUI privileged Discord pre-TLS probe: staged/unsupported; owner-run read-only diagnostics remain,
  but P02 does not root-import GUI merely to read counters.
- blockcheck remains a separate explicit development/experimental lane and is not authority for the
  standard runtime executor.
- zapret2 vendored switch is P03, not P02.

## UserTestSpace

```bash
bash meta_tools/uts_prepare.sh --p02
bash meta_tools/uts_prepare.sh --full
```

Both commands disable pytest cache and Python bytecode; the metatool removes generated test
artifacts after execution. `devctl start` still does not require pytest.
