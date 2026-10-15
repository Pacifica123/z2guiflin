from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import pytest

from zap2_gui.adapters.orchestrator_candidates import (
    build_orchestrated_profile,
    circular_switches_from_log,
    list_orchestrator_candidates,
)
from zap2_gui.adapters.preset_editor import (
    EditableTrafficProfile,
    PRESET_PROTOCOL_TCP,
    PRESET_TARGET_DOMAINS,
    add_owner_preset_profile,
    create_owner_preset,
)
from zap2_gui.adapters.presets import load_preset
from zap2_gui.models.orchestrator import (
    OrchestratedProfile,
    circular_switches_to_text,
    parse_circular_log,
    referenced_lua_functions,
)

ROOT = Path(__file__).resolve().parents[1]
LUA_DIRS = (ROOT / "core/zapret2/lua", ROOT / "core/overlays/zapret2/lua")


def _lua_functions() -> set[str]:
    names: set[str] = set()
    for folder in LUA_DIRS:
        for path in folder.glob("*.lua"):
            names.update(re.findall(r"^function\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", path.read_text(encoding="utf-8", errors="replace"), re.M))
    return names


def _profile(**kwargs) -> OrchestratedProfile:
    base = dict(
        candidates=(("fake:blob=fake_default_tls:repeats=1",), ("--lua-desync=fake:blob=fake_default_tls:tcp_md5", "multidisorder:pos=1,midsld")),
        params={"fails": 3, "time": 60},
    )
    base.update(kwargs)
    return OrchestratedProfile(**base)


def test_render_matches_upstream_circular_scheme() -> None:
    args = _profile(final_last=True, payload="tls_client_hello", params={"fails": 4, "time": 30, "nld": 2, "reqhost": True, "key": "k1"}).to_strategy_args()
    assert args == (
        "--out-range=-s34228",
        "--in-range=-s5556",
        "--lua-desync=circular:fails=4:time=30:nld=2:reqhost:key=k1",
        "--in-range=x",
        "--payload=tls_client_hello",
        "--lua-desync=fake:blob=fake_default_tls:repeats=1:strategy=1",
        "--lua-desync=fake:blob=fake_default_tls:tcp_md5:strategy=2:final",
        "--lua-desync=multidisorder:pos=1,midsld:strategy=2",
    )


def test_strategy_tags_have_no_gaps() -> None:
    args = OrchestratedProfile(candidates=(("a",), ("b",), ("c", "d"))).to_strategy_args()
    tags = [int(m) for arg in args for m in re.findall(r":strategy=(\d+)", arg)]
    assert sorted(set(tags)) == [1, 2, 3]


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"candidates": (("fake",),)}, "минимум 2"),
        ({"candidates": (("fake",), ())}, "пуста"),
        ({"params": {"retries": 3}}, "Неизвестный параметр"),
        ({"params": {"fails": 0}}, "fails"),
        ({"params": {"reqhost": "yes"}}, "флаг"),
        ({"params": {"key": "a:b"}}, "key"),
        ({"candidates": (("fake:strategy=1",), ("multisplit",))}, "автоматически"),
        ({"candidates": (("fake",), ("circular",))}, "circular"),
        ({"candidates": (("fake",), ("--payload=tls_client_hello",))}, "только --lua-desync"),
    ],
)
def test_invalid_input_rejected_with_russian_text(kwargs, message) -> None:
    with pytest.raises(ValueError, match=message):
        _profile(**kwargs).to_strategy_args()


def test_rendered_args_reference_only_existing_lua_functions() -> None:
    known = _lua_functions()
    assert "circular" in known
    args = _profile(final_last=True).to_strategy_args()
    assert set(referenced_lua_functions(args)) <= known
    example = json.loads((ROOT / "strategies/orchestrated-circular-example.json").read_text(encoding="utf-8"))
    assert set(referenced_lua_functions(example["runtimeArgs"])) <= known
    assert "--lua-init=@core/zapret2/lua/zapret-auto.lua" in example["runtimeArgs"]
    assert example["experimental"] is True


def test_candidates_come_from_strategy_catalog_and_example_is_reproducible() -> None:
    candidates = {item.strategy_id: item for item in list_orchestrator_candidates(ROOT)}
    assert "orchestrated-circular-example" not in candidates
    example = json.loads((ROOT / "strategies/orchestrated-circular-example.json").read_text(encoding="utf-8"))
    meta = example["orchestrator"]
    profile = build_orchestrated_profile(meta["candidates"], root=ROOT, params=meta["params"], final_last=meta["final"])
    tail = list(profile.to_strategy_args())
    assert example["runtimeArgs"][-len(tail):] == tail
    with pytest.raises(ValueError, match="не найдена"):
        build_orchestrated_profile(["missing", "also-missing"], root=ROOT)


def test_owner_preset_gets_auto_lua_init_for_circular(tmp_path: Path) -> None:
    target = tmp_path / "project"
    shutil.copytree(ROOT, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache", ".git"))
    created = create_owner_preset("Circular test", root=target)
    profile = EditableTrafficProfile(
        name="TLS circular",
        protocol=PRESET_PROTOCOL_TCP,
        ports="443",
        l7="tls",
        target_kind=PRESET_TARGET_DOMAINS,
        target_value="example.com",
        strategy_args=_profile(payload="tls_client_hello").to_strategy_args(),
    )
    add_owner_preset_profile(created.preset_id, profile, root=target)
    preset = load_preset(created.preset_id, root=target).preset
    assert "--lua-init=@core/zapret2/lua/zapret-auto.lua" in preset.global_args


LOG = """\
automate: host record key 'autostate.tls443.example.com'
circular: start from strategy 1
circular: current strategy 1
automate: host record key 'autostate.tls443.example.com'
standard_failure_detector: incoming RST s1 in range s4096
automate: failure detected
automate: failure counter 3/3
circular: rotate strategy to 2
circular: final strategy 2 reached. will rotate no more.
circular: current strategy 2
automate: host record key 'autostate.tls443.other.org'
standard_failure_detector: retransmission 3/3
automate: failure detected
circular: rotate strategy to 2
"""


def test_parse_circular_log(tmp_path: Path) -> None:
    switches = parse_circular_log(LOG.splitlines())
    assert len(switches) == 2
    first, second = switches
    assert (first.host, first.from_strategy, first.to_strategy, first.reason, first.key, first.final) == (
        "example.com", 1, 2, "rst", "tls443", True
    )
    assert (second.host, second.from_strategy, second.to_strategy, second.reason) == ("other.org", None, 2, "retransmission")
    text = circular_switches_to_text(switches)
    assert "example.com: стратегия 1 → 2" in text
    log = tmp_path / "nfqws2.log"
    log.write_text(LOG, encoding="utf-8")
    assert circular_switches_from_log(log) == switches
    assert circular_switches_from_log(tmp_path / "missing.log") == ()
    assert circular_switches_to_text(()) == "Переключений circular в логе нет."


def test_parser_uses_exact_lua_log_texts() -> None:
    lua = (ROOT / "core/zapret2/lua/zapret-auto.lua").read_text(encoding="utf-8")
    for fragment in (
        'DLOG("circular: rotate strategy to "',
        'DLOG("circular: current strategy "',
        "automate: host record key 'autostate.",
        "standard_failure_detector: incoming RST s",
        "standard_failure_detector: retransmission ",
    ):
        assert fragment in lua


def test_gui_source_exposes_circular_mode() -> None:
    source = (ROOT / "gui/zap2_gui/widgets/preset_constructor.py").read_text(encoding="utf-8")
    assert "Оркестратор (circular" in source
    assert "build_orchestrated_profile" in source


def test_orchestrator_modules_are_in_shipping_allowlist() -> None:
    import json
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    files = set(json.loads((root / "packaging/release-files.json").read_text(encoding="utf-8"))["files"])
    for rel in ("gui/zap2_gui/models/orchestrator.py", "gui/zap2_gui/adapters/orchestrator_candidates.py",
                "strategies/orchestrated-circular-example.json", "presets/workspace/orchestrated-circular-example.txt"):
        assert rel in files, rel
