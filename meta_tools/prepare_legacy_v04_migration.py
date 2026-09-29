#!/usr/bin/env python3
"""Authorize safe one-time migration of a stale pre-P02/v0.4 nft table."""
from __future__ import annotations

import argparse
from pathlib import Path

from zap2_gui.adapters.privileged_executor import BoundedNftRunner
from zap2_gui.adapters.runtime_apply import authorize_stale_legacy_v04_table


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--profile", default="default")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    result = authorize_stale_legacy_v04_table(root, args.profile, runner=BoundedNftRunner(root))
    print(f"Legacy v0.4 nft migration: {result.get('state')}")
    print(f"table: {result.get('nftTable')}")
    if result.get("queueNums") is not None:
        print("queue nums:", ", ".join(str(x) for x in result.get("queueNums", [])) or "none")
    if result.get("activeQueueNums"):
        print("active queue nums:", ", ".join(str(x) for x in result["activeQueueNums"]))
    if result.get("path"):
        print(f"consent receipt: {result['path']}")
    print(f"message: {result.get('message')}")
    state = result.get("state")
    return 0 if state in {"absent", "authorized"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
