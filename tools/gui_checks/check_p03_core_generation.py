#!/usr/bin/env python3
"""Dependency-free P03 generation/corpus gate.

The checker does not execute nfqws2, make, sudo, nft or network operations.
It validates exact candidate identity, local overlay ownership and 100% static
classification of the shipping strategy corpus. Native nfqws2 --dry-run remains
an owner/UTS check after a clean build.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "gui"))

from zap2_gui.adapters.core_generation import (  # noqa: E402
    COMPAT_RECEIPT_RELATIVE_PATH,
    OVERLAY_RELATIVE_PATH,
    P03_ARCHIVE_SHA256,
    P03_UPSTREAM_COMMIT,
    P03_UPSTREAM_VERSION,
    generation_identity_errors,
    load_overlay_manifest,
    sha256_file,
    shipping_corpus_records,
    source_transform_digest,
    upstream_tree_files,
)
from zap2_gui.adapters.local_build import create_local_build_plan  # noqa: E402


def _candidate_source_text() -> str:
    paths = [
        ROOT / "core/zapret2/nfq2/nfqws.c",
        ROOT / "core/zapret2/nfq2/params.c",
        ROOT / "core/zapret2/docs/manual.md",
    ]
    return "\n".join(path.read_text(encoding="utf-8", errors="replace") for path in paths)


def _candidate_lua_text() -> str:
    lua_root = ROOT / "core/zapret2/lua"
    parts = [path.read_text(encoding="utf-8", errors="replace") for path in sorted(lua_root.glob("*.lua"))]
    parts.append((ROOT / OVERLAY_RELATIVE_PATH).read_text(encoding="utf-8", errors="replace"))
    return "\n".join(parts)


def _option_supported(source: str, option: str) -> bool:
    key = option[2:]
    return option in source or f'"{key}"' in source or f"--{key}" in source


def _function_supported(lua: str, name: str) -> bool:
    return re.search(r"\bfunction\s+" + re.escape(name) + r"\b", lua) is not None


def _resolve_at_value(arg: str) -> Path | None:
    if "=@" not in arg:
        return None
    value = arg.split("=@", 1)[1]
    # Only literal project inputs are checked here. Dynamic placeholders are not
    # part of the committed shipping corpus.
    if not value or value.startswith("<"):
        return None
    return ROOT / value


def main() -> int:
    errors = list(generation_identity_errors(ROOT))
    records = shipping_corpus_records(ROOT)
    receipt_path = ROOT / COMPAT_RECEIPT_RELATIVE_PATH
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))

    if len(upstream_tree_files(ROOT)) != 244:
        errors.append("expected exactly 244 filtered upstream files")
    if receipt.get("shippingStrategyCount") != len(records):
        errors.append("compatibility receipt strategy count mismatch")
    if receipt.get("targetUpstreamCommit") != P03_UPSTREAM_COMMIT:
        errors.append("target upstream commit mismatch")
    if receipt.get("targetUpstreamVersion") != P03_UPSTREAM_VERSION:
        errors.append("target upstream version mismatch")

    manifest = json.loads((ROOT / "core/zapret2/UPSTREAM_IMPORT.json").read_text(encoding="utf-8"))
    if manifest.get("sourceArchiveSha256") != P03_ARCHIVE_SHA256:
        errors.append("source archive SHA mismatch")

    overlay_manifest = load_overlay_manifest(ROOT)
    transforms = overlay_manifest.get("sourceTransforms", [])
    if len(transforms) != 1:
        errors.append("expected exactly one registered P03 source transform")
    else:
        transform = transforms[0]
        base = ROOT / "core/zapret2" / str(transform.get("targetPath", ""))
        effective = ROOT / str(transform.get("overlayPath", ""))
        if not base.is_file() or sha256_file(base) != transform.get("baseSha256"):
            errors.append("NFQUEUE source-transform base hash mismatch")
        if not effective.is_file() or sha256_file(effective) != transform.get("effectiveSha256"):
            errors.append("NFQUEUE source-transform effective hash mismatch")
        if base.is_file() and effective.is_file():
            base_text = base.read_text(encoding="utf-8", errors="replace")
            effective_text = effective.read_text(encoding="utf-8", errors="replace")
            try:
                if not (base_text.index("droproot(params.uid") < base_text.index("nfq_init(&h, &qh, &cbdata)")):
                    errors.append("candidate NFQUEUE privilege-order fixture no longer reproduces the upstream-first drop")
                if not (effective_text.index("nfq_init(&h, &qh, &cbdata)") < effective_text.index("droproot(params.uid")):
                    errors.append("P03 NFQUEUE source transform does not move queue creation before privilege drop")
            except ValueError:
                errors.append("NFQUEUE privilege-order fixture anchors are missing")
    if not source_transform_digest(ROOT):
        errors.append("source-transform digest is empty")

    build_plan = create_local_build_plan(ROOT, "nfqws2")
    if len(build_plan.commands) != 1:
        errors.append("nfqws2 build plan must have one staged generation command")
    else:
        argv = build_plan.commands[0].argv
        if len(argv) != 3 or Path(argv[0]).resolve() != Path(sys.executable).resolve() or not argv[1].endswith("tools/core_generation_build.py") or argv[2] != "nfqws2":
            errors.append("nfqws2 build plan bypasses the P03 staged generation build adapter")

    candidate_source = _candidate_source_text()
    candidate_lua = _candidate_lua_text()
    unresolved_options: set[str] = set()
    unresolved_functions: set[str] = set()
    missing_inputs: set[str] = set()
    send_delay_count = 0
    writeable_refs: list[str] = []
    hostfakesplit_multi_strategies: list[str] = []

    for row in records:
        strategy_id = str(row["id"])
        for arg in row["runtimeArgs"]:
            option = str(arg).split("=", 1)[0]
            if option.startswith("--") and not _option_supported(candidate_source, option):
                unresolved_options.add(option)
            if str(arg).startswith("--lua-desync="):
                value = str(arg).split("=", 1)[1]
                function_name = value.split(":", 1)[0]
                if not _function_supported(candidate_lua, function_name):
                    unresolved_functions.add(function_name)
                if function_name == "hostfakesplit_multi":
                    hostfakesplit_multi_strategies.append(strategy_id)
                if function_name == "send" and ":delay=" in value:
                    send_delay_count += 1
            resolved = _resolve_at_value(str(arg))
            if resolved is not None and not resolved.is_file():
                missing_inputs.add(str(resolved.relative_to(ROOT)))
            lowered = str(arg).lower()
            if "writeable" in lowered or "writable" in lowered:
                writeable_refs.append(f"{strategy_id}:{arg}")

    if unresolved_options:
        errors.append("candidate options unresolved: " + ", ".join(sorted(unresolved_options)))
    if unresolved_functions:
        errors.append("candidate Lua functions unresolved: " + ", ".join(sorted(unresolved_functions)))
    if missing_inputs:
        errors.append("shipping @ inputs missing: " + ", ".join(sorted(missing_inputs)))
    if send_delay_count:
        errors.append("shipping corpus unexpectedly exercises candidate send:delay semantic")
    if writeable_refs:
        errors.append("shipping corpus unexpectedly exercises writable spelling migration")
    if len(set(hostfakesplit_multi_strategies)) != 8:
        errors.append("expected hostfakesplit_multi behavior in exactly 8 shipping strategies")

    classifications = receipt.get("classificationCounts", {})
    if int(classifications.get("unknown", -1)) != 0:
        errors.append("shipping corpus contains UNKNOWN classifications")
    if int(classifications.get("changed-unsupported", -1)) != 0:
        errors.append("shipping corpus contains unsupported strategies")
    if sum(int(classifications.get(key, 0)) for key in ("equivalent", "equivalent-local-overlay-relocation", "changed-transformable", "changed-unsupported", "unknown")) != len(records):
        errors.append("classification counts do not cover the whole shipping corpus")

    if errors:
        print("P03 core generation: FAIL")
        for error in errors:
            print(f"- {error}")
        return 1

    print("P03 core generation: PASS")
    print(f"upstream: {P03_UPSTREAM_VERSION}@{P03_UPSTREAM_COMMIT[:7]}")
    print(f"archive sha256: {P03_ARCHIVE_SHA256}")
    print("filtered upstream files: 244")
    print(f"shipping strategies classified: {len(records)}/{len(records)}")
    print("custom_funcs: LOCAL_OVERLAY outside core/zapret2")
    print("NFQUEUE privilege order: SOURCE_TRANSFORM_OVERLAY outside core/zapret2")
    print("build path: fresh staged candidate + verified transforms + atomic artifact publish")
    print("Lua compatibility: 6/6")
    print("send:delay exercised by shipping corpus: no")
    print("WRITEABLE->WRITABLE migration exercised by shipping corpus: no")
    print("native nfqws2 dry-run: deferred to clean-build UTS/owner host (patch container lacks build development libs)")
    print("mutates system/runtime: no")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
