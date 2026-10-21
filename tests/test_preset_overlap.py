from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from zap2_gui.adapters.preset_editor import (
    EditableTrafficProfile,
    PRESET_PROTOCOL_TCP,
    PRESET_TARGET_DOMAINS,
    PRESET_TARGET_NONE,
    add_owner_preset_profile,
    add_owner_profile_exclusions,
    copy_preset_for_editing,
    create_owner_preset,
    editable_profile_from_runtime,
    is_preset_editor_managed,
)
from zap2_gui.adapters.presets import load_preset
from zap2_gui.models.preset import parse_preset_args
from zap2_gui.models.profile_overlap import (
    DomainSet,
    SimulatedConnection,
    file_list_resolver,
    find_overlaps,
    parse_ports,
    simulate_first_match,
)

ROOT = Path(__file__).resolve().parents[1]
LUA = "--lua-desync=multisplit:pos=1"


def _preset(*profiles: tuple[str, ...]):
    args: list[str] = ["--lua-init=@core/zapret2/lua/zapret-lib.lua"]
    for index, profile in enumerate(profiles):
        if index:
            args.append("--new")
        args.extend(profile)
        args.append(LUA)
    return parse_preset_args(args, preset_id="t")


def test_ports_ranges_and_negation() -> None:
    assert parse_ports(["443", "80", "81-90"]) == ((80, 90), (443, 443))
    assert parse_ports(["*"]) == ((0, 65535),)
    assert parse_ports(["~443"]) == ((0, 442), (444, 65535))


def test_domain_set_matches_subdomains_and_caret_exact() -> None:
    hosts = DomainSet.from_items(["youtube.com", "^ytimg.com"])
    assert hosts.covers("www.youtube.com") and hosts.covers("youtube.com")
    assert hosts.covers("ytimg.com") and not hosts.covers("i.ytimg.com")
    assert hosts.touches_entry("com") is True  # набор лежит внутри более общей записи


def test_generic_profile_above_specific_shadows_it_completely() -> None:
    preset = _preset(("--name=all 443", "--filter-tcp=443"), ("--name=discord", "--filter-tcp=443", "--hostlist-domains=discord.com"))
    overlaps = find_overlaps(preset)
    assert len(overlaps) == 1
    item = overlaps[0]
    assert item.severity == "error" and (item.earlier, item.later) == (0, 1)
    assert "никогда не сработает" in item.message
    kinds = {fix.kind for fix in item.fixes}
    assert kinds == {"move-above", "exclude-domains"}
    assert next(fix for fix in item.fixes if fix.kind == "exclude-domains").domains == ("discord.com",)


def test_specific_above_generic_is_the_intended_order() -> None:
    preset = _preset(("--filter-tcp=443", "--hostlist-domains=discord.com"), ("--filter-tcp=80,443",))
    assert find_overlaps(preset) == ()


def test_partial_domain_overlap_lists_shared_domains() -> None:
    preset = _preset(
        ("--filter-tcp=443", "--hostlist-domains=youtube.com,googlevideo.com"),
        ("--filter-tcp=443", "--hostlist-domains=youtube.com,discord.com"),
    )
    (item,) = find_overlaps(preset)
    assert item.severity == "warning"
    assert item.shared_domains == ("youtube.com",)


def test_disjoint_ports_and_exclusions_remove_overlap() -> None:
    assert find_overlaps(_preset(("--filter-tcp=80",), ("--filter-tcp=443", "--hostlist-domains=a.com"))) == ()
    excluded = _preset(
        ("--filter-tcp=443", "--hostlist-domains=example.org", "--hostlist-exclude-domains=discord.com"),
        ("--filter-tcp=443", "--hostlist-domains=discord.com"),
    )
    assert find_overlaps(excluded) == ()


def test_ranges_are_not_profile_filters() -> None:
    """--out-range внутрипрофильный: два профиля, отличающиеся только им, — второй мёртв."""

    preset = _preset(
        ("--filter-tcp=443", "--ipset-ip=162.159.128.233", "--out-range=<s1"),
        ("--filter-tcp=443", "--ipset-ip=162.159.128.233", "--out-range=s1<d1"),
    )
    (item,) = find_overlaps(preset)
    assert item.severity == "error"


def test_unreadable_hostlist_gives_no_guess(tmp_path: Path) -> None:
    preset = _preset(("--filter-tcp=443", "--hostlist=lists/missing.txt"), ("--filter-tcp=443", "--hostlist-domains=a.com"))
    assert find_overlaps(preset, file_list_resolver(tmp_path)) == ()
    (tmp_path / "lists").mkdir()
    (tmp_path / "lists" / "missing.txt").write_text("# comment\na.com\n", encoding="utf-8")
    (item,) = find_overlaps(preset, file_list_resolver(tmp_path))
    assert item.severity == "error"


def test_simulator_picks_first_match_and_explains_skips() -> None:
    preset = _preset(
        ("--name=voice", "--filter-udp=50000-65535"),
        ("--name=yt", "--filter-tcp=443", "--filter-l7=tls", "--hostlist-domains=youtube.com"),
        ("--name=all", "--filter-tcp=80,443"),
    )
    result = simulate_first_match(preset, SimulatedConnection("tcp", 443, host="www.youtube.com"))
    assert result.winner == 1
    assert result.steps[0].matched is False and "UDP" in result.steps[0].reason
    other = simulate_first_match(preset, SimulatedConnection("tcp", 443, host="example.com"))
    assert other.winner == 2
    nohost = simulate_first_match(preset, SimulatedConnection("tcp", 443))
    assert nohost.winner == 2 and "имя хоста" in nohost.steps[1].reason
    nothing = simulate_first_match(preset, SimulatedConnection("udp", 53))
    assert nothing.winner is None and "без обработки" in nothing.to_text()


def test_simulator_exclusions_and_hostname_rule() -> None:
    preset = _preset(("--filter-tcp=443", "--hostlist-exclude-domains=bank.ru"), ("--filter-tcp=443",))
    assert simulate_first_match(preset, SimulatedConnection("tcp", 443, host="online.bank.ru")).winner == 1
    # профиль только с исключающим листом без имени хоста не выбирается (nfqws2 desync.c dp_match)
    assert simulate_first_match(preset, SimulatedConnection("tcp", 443)).winner == 1
    globally = simulate_first_match(preset, SimulatedConnection("tcp", 443, host="bank.ru"), global_exclude_hosts=("bank.ru",))
    assert globally.winner is None and globally.globally_excluded == "bank.ru"
    by_ip = simulate_first_match(preset, SimulatedConnection("tcp", 443, ip="10.1.2.3"), global_exclude_nets=("10.0.0.0/8",))
    assert by_ip.globally_excluded == "10.1.2.3"


def _project_copy(tmp_path: Path) -> Path:
    target = tmp_path / "project"
    shutil.copytree(ROOT, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache", ".git"))
    return target


def test_profile_exclusions_round_trip_through_editor(tmp_path: Path) -> None:
    root = _project_copy(tmp_path)
    created = create_owner_preset("Overlap test", root=root)
    profile = EditableTrafficProfile(
        name="All 443",
        protocol=PRESET_PROTOCOL_TCP,
        ports="443",
        target_kind=PRESET_TARGET_NONE,
        exclude_ips="10.0.0.0/8 192.168.0.0/16",
        strategy_args=(LUA,),
    )
    assert "--ipset-exclude-ip=10.0.0.0/8,192.168.0.0/16" in profile.to_raw_args()
    add_owner_preset_profile(created.preset_id, profile, root=root)
    add_owner_preset_profile(
        created.preset_id,
        EditableTrafficProfile(name="Discord", protocol=PRESET_PROTOCOL_TCP, ports="443",
                               target_kind=PRESET_TARGET_DOMAINS, target_value="discord.com", strategy_args=(LUA,)),
        root=root,
    )
    overlaps = find_overlaps(load_preset(created.preset_id, root).preset)
    fix = next(item for item in overlaps[0].fixes if item.kind == "exclude-domains")
    add_owner_profile_exclusions(created.preset_id, fix.profile_index, domains=fix.domains, root=root)
    preset = load_preset(created.preset_id, root).preset
    assert find_overlaps(preset) == ()
    first = preset.profiles[0]
    assert "--hostlist-exclude-domains=discord.com" in first.raw_args
    editable = editable_profile_from_runtime(first)
    assert editable.exclude_domains == "discord.com"
    assert editable.exclude_ips == "10.0.0.0/8 192.168.0.0/16"
    assert set(editable.to_raw_args()) == set(first.raw_args)


def test_bad_exclusion_values_are_rejected() -> None:
    with pytest.raises(ValueError, match="Исключения IP"):
        EditableTrafficProfile(name="x", protocol=PRESET_PROTOCOL_TCP, ports="443", exclude_ips="10.0.0.0/33",
                               strategy_args=(LUA,)).validate()


def test_copy_makes_editable_preset_with_same_args(tmp_path: Path) -> None:
    root = _project_copy(tmp_path)
    source = load_preset("community-discord-syndata-edge-flow-v2b", root)
    assert not is_preset_editor_managed(source.preset.preset_id, root)
    copied = copy_preset_for_editing(source.preset.preset_id, root)
    again = copy_preset_for_editing(source.preset.preset_id, root)
    assert copied.preset_id != again.preset_id
    assert is_preset_editor_managed(copied.preset_id, root)
    copy_entry = load_preset(copied.preset_id, root)
    assert copy_entry.preset.to_runtime_args() == source.preset.to_runtime_args()
    assert copy_entry.metadata.source_preset["copiedFromPresetId"] == source.preset.preset_id


def test_presets_page_marks_dead_profiles_and_offers_copy(tmp_path: Path, monkeypatch) -> None:
    pytest.importorskip("PyQt6")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PyQt6 import QtCore
    from PyQt6.QtWidgets import QApplication, QListWidget, QPushButton, QTableWidget

    from zap2_gui.widgets.presets import _chip_role, make_presets_page

    app = QApplication.instance() or QApplication([])
    root = _project_copy(tmp_path)
    settings = QtCore.QSettings(str(tmp_path / "settings.ini"), QtCore.QSettings.Format.IniFormat)
    page = make_presets_page(root, settings)
    lists = [item for item in page.findChildren(QListWidget) if item.toolTip().startswith("Клик")]
    (preset_list,) = lists
    ids = [str(preset_list.item(i).data(QtCore.Qt.ItemDataRole.UserRole)) for i in range(preset_list.count())]
    row = ids.index("community-discord-syndata-edge-flow-v2b")
    chips = preset_list.item(row).data(_chip_role())["chips"]
    assert ("встроенный", "muted") in chips
    assert any(text.startswith("✖ мёртвых профилей") for text, _tone in chips)
    preset_list.setCurrentRow(row)
    app.processEvents()
    table = next(item for item in page.findChildren(QTableWidget) if item.columnCount() == 6 and item.rowCount() == 7)
    assert table.item(1, 1).text().startswith("✖ ")
    assert not table.dragEnabled()  # встроенный пресет: порядок не меняется
    copy_button = next(item for item in page.findChildren(QPushButton) if item.text() == "Копия для правки")
    assert copy_button.isEnabled()
    page.close()


def test_presets_page_copy_then_one_click_fix_and_drag_order(tmp_path: Path, monkeypatch) -> None:
    pytest.importorskip("PyQt6")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PyQt6 import QtCore
    from PyQt6.QtWidgets import QApplication, QInputDialog, QListWidget, QPushButton, QTableWidget

    from zap2_gui.widgets.presets import make_presets_page

    app = QApplication.instance() or QApplication([])
    root = _project_copy(tmp_path)
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *args, **kwargs: ("v2b mine", True)))
    settings = QtCore.QSettings(str(tmp_path / "settings.ini"), QtCore.QSettings.Format.IniFormat)
    page = make_presets_page(root, settings)
    (preset_list,) = [item for item in page.findChildren(QListWidget) if item.toolTip().startswith("Клик")]
    ids = [str(preset_list.item(i).data(QtCore.Qt.ItemDataRole.UserRole)) for i in range(preset_list.count())]
    preset_list.setCurrentRow(ids.index("community-discord-syndata-edge-flow-v2b"))
    next(item for item in page.findChildren(QPushButton) if item.text() == "Копия для правки").click()
    app.processEvents()
    copy_id = str(preset_list.currentItem().data(QtCore.Qt.ItemDataRole.UserRole))
    assert copy_id.startswith("v2b-mine")
    table = next(item for item in page.findChildren(QTableWidget) if item.columnCount() == 6 and item.rowCount() == 7)
    assert table.dragEnabled()

    overlap_list = next(item for item in page.findChildren(QListWidget) if item.minimumHeight() == 48)
    overlap_list.setCurrentRow(0)
    fix = next(item for item in page.findChildren(QPushButton) if item.text() == "Поднять #2 над #1")
    assert fix.isEnabled()
    before = [profile.name for profile in load_preset(copy_id, root).preset.profiles]
    fix.click()
    after = [profile.name for profile in load_preset(copy_id, root).preset.profiles]
    assert after[:2] == [before[1], before[0]] and after[2:] == before[2:]
    page.close()


def test_drop_target_index_matches_pop_insert() -> None:
    from zap2_gui.widgets.presets import drop_target_index

    assert drop_target_index(3, 0, False, 5) == 0  # над первой строкой
    assert drop_target_index(0, 2, True, 5) == 2  # под третьей
    assert drop_target_index(0, 2, False, 5) == 1  # над третьей
    assert drop_target_index(1, -1, False, 5) == 4  # в пустое место внизу
    assert drop_target_index(2, 2, False, 5) == 2  # на себя
