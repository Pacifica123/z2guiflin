from __future__ import annotations

from pathlib import Path

from zap2_gui.adapters.strat_collection import load_strat_collection
from zap2_gui.adapters.strat_collection_port import analyze_strat_port

ROOT = Path(__file__).resolve().parents[1]


def _plans() -> dict:
    return {e.entry_id: analyze_strat_port(e, ROOT) for e in load_strat_collection(ROOT).entries}


def test_most_of_the_collection_now_ports() -> None:
    plans = _plans()
    ported = [p for p in plans.values() if p.can_port]
    # Было 2 из 55; оставшиеся упираются в --dup и ipfrag2 — у них нет однозначного аналога.
    assert len(ported) >= 45, len(ported)
    leftovers = {item.split("=")[0] for p in plans.values() if not p.can_port for item in p.unsupported}
    assert leftovers <= {"--dup", "--dup-cutoff", "--dup-fooling", "--dup-autottl", "--dpi-desync",
                         "fake: для этого протокола нет однозначного payload/blob mapping"}, leftovers


def test_hex_blobs_are_inline_not_files() -> None:
    for plan in _plans().values():
        assert not any("blob отсутствует: 0x" in item for item in plan.unsupported)
        assert not any(arg.startswith("--blob=") and ":@" not in arg for arg in plan.runtime_args)
    udplen = [arg for p in _plans().values() for arg in p.runtime_args if arg.startswith("--lua-desync=udplen")]
    assert any("pattern=0xDEADBEEF" in arg for arg in udplen)


def test_wssize_detached_value_and_syn_friendly_profile() -> None:
    entry = next(e for e in load_strat_collection(ROOT).entries if e.entry_id == "md5sigpadencapwssize")
    assert "--wssize=1:6" in entry.winws_args
    plan = analyze_strat_port(entry, ROOT)
    assert plan.can_port
    assert "--lua-desync=wssize:wsize=1:scale=6" in plan.runtime_args
    profile = plan.runtime_args[plan.runtime_args.index("--lua-desync=wssize:wsize=1:scale=6") - 1:]
    head = profile[: profile.index("--new")] if "--new" in profile else profile
    assert "--filter-l7=tls" not in head


def test_every_ported_entry_survives_parser_round_trip() -> None:
    from zap2_gui.models.preset import parse_preset_args

    for entry_id, plan in _plans().items():
        if plan.can_port:
            parsed = parse_preset_args(plan.runtime_args, preset_id="t", title=entry_id)
            assert parsed.to_runtime_args() == plan.runtime_args
