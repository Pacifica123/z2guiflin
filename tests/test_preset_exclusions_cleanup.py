from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pytest

from zap2_gui.adapters.execution_plan import materialize_execution_plan
from zap2_gui.adapters.preset_editor import can_remove_preset, remove_generated_preset, remove_presets
from zap2_gui.adapters.preset_exclusions import (
    GlobalExclusions,
    apply_global_exclusions,
    exclusion_coverage,
    load_global_exclusions,
    normalize_exclusions,
    save_global_exclusions,
)
from zap2_gui.adapters.presets import load_preset, load_preset_catalog, select_preset
from zap2_gui.models.preset import parse_preset_args
from zap2_gui.models.preset_labels import blockcheck_title, display_title

ROOT = Path(__file__).resolve().parents[1]
LUA = "--lua-desync=multisplit:pos=1"


def _project_copy(tmp_path: Path) -> Path:
    target = tmp_path / "project"
    shutil.copytree(ROOT, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache", ".git"))
    return target


def test_normalize_rejects_garbage_and_whole_internet() -> None:
    value = normalize_exclusions(["Sberbank.ru.", "https://gosuslugi.ru/path", "^exact.ru", "sberbank.ru"], ["192.168.1.7/16"])
    assert value.domains == ("sberbank.ru", "gosuslugi.ru", "^exact.ru")
    assert value.cidrs == ("192.168.0.0/16",)
    with pytest.raises(ValueError, match="не домен"):
        normalize_exclusions(["localhost"], [])
    with pytest.raises(ValueError, match="весь интернет"):
        normalize_exclusions([], ["0.0.0.0/0"])


def test_domains_go_only_to_profiles_with_domain_lists() -> None:
    args = (
        "--lua-init=@core/zapret2/lua/zapret-lib.lua",
        "--filter-tcp=443", "--ipset-ip=162.159.128.233", "--out-range=<s1", LUA,
        "--new", "--name=yt", "--filter-tcp=443", "--hostlist-domains=youtube.com", LUA,
    )
    exclusions = GlobalExclusions(("sberbank.ru",), ("10.0.0.0/8",))
    result = apply_global_exclusions(args, exclusions)
    preset = parse_preset_args(result, preset_id="x")
    first, second = preset.profiles
    assert "--hostlist-exclude-domains=sberbank.ru" not in first.raw_args  # IP-профиль: имя хоста ещё неизвестно на SYN
    assert "--ipset-exclude-ip=10.0.0.0/8" in first.raw_args
    assert "--hostlist-exclude-domains=sberbank.ru" in second.raw_args
    assert second.raw_args.index("--hostlist-exclude-domains=sberbank.ru") < second.raw_args.index(LUA)
    assert preset.global_args == ("--lua-init=@core/zapret2/lua/zapret-lib.lua",)
    assert apply_global_exclusions(args, GlobalExclusions()) == args
    assert exclusion_coverage(args, exclusions) == (1, 2)


def test_plan_carries_global_exclusions_and_preset_files_stay(tmp_path: Path) -> None:
    root = _project_copy(tmp_path)
    before = materialize_execution_plan(root).plan.runtime_args
    preset_file = (root / "presets" / "workspace" / "manual-local.txt").read_bytes()
    save_global_exclusions(root, normalize_exclusions([], ["192.168.0.0/16"]))
    assert load_global_exclusions(root).cidrs == ("192.168.0.0/16",)
    after = materialize_execution_plan(root).plan.runtime_args
    assert after != before
    assert sum(1 for arg in after if arg == "--ipset-exclude-ip=192.168.0.0/16") == len(parse_preset_args(before, preset_id="p").profiles)
    assert (root / "presets" / "workspace" / "manual-local.txt").read_bytes() == preset_file


def test_readable_blockcheck_titles() -> None:
    when = datetime(2026, 10, 21, 11, 30, tzinfo=timezone.utc)
    title = blockcheck_title("YouTube", ("fake", "multisplit"), "googlevideo.com", when)
    assert title.startswith("YouTube: fake + multisplit · googlevideo.com · 21.10.2026 ")
    old = display_title(
        "Blockcheck YouTube / www.youtube.com #03",
        {"id": "blockcheck-generated", "target": "www.youtube.com", "generatedAt": "2026-10-21T11:30:00Z"},
        {"title": "YouTube"},
        ("--filter-tcp=443", "--lua-desync=fake:blob=x", "--lua-desync=multidisorder:pos=1"),
    )
    assert old.startswith("YouTube: fake + multidisorder · www.youtube.com · 21.10.2026")
    assert display_title("Мой пресет", {"id": "blockcheck-generated"}, None, ()) == "Мой пресет"


def _write_generated(root: Path, strategy_id: str) -> None:
    preset_rel = f"presets/generated/{strategy_id}.txt"
    (root / "presets" / "generated").mkdir(parents=True, exist_ok=True)
    (root / "strategies" / "generated").mkdir(parents=True, exist_ok=True)
    args = ["--lua-init=@core/zapret2/lua/zapret-lib.lua", "--lua-init=@core/zapret2/lua/zapret-antidpi.lua",
            "--filter-tcp=443", "--payload=tls_client_hello", "--lua-desync=multisplit:pos=1"]
    (root / preset_rel).write_text("# generated\n" + "\n".join(args) + "\n", encoding="utf-8")
    template = json.loads((root / "strategies" / "manual-local.json").read_text(encoding="utf-8"))
    template.update({
        "id": strategy_id,
        "title": "Blockcheck YouTube / www.youtube.com #01",
        "runtimeArgs": args,
        "presetPath": preset_rel,
        "serviceTarget": {"presetId": "youtube", "title": "YouTube", "targets": ["www.youtube.com"]},
        "sourcePreset": {"engine": "nfqws2", "id": "blockcheck-generated", "target": "www.youtube.com",
                         "generatedAt": "2026-10-21T11:30:00Z"},
    })
    (root / "strategies" / "generated" / f"{strategy_id}.json").write_text(json.dumps(template), encoding="utf-8")
    catalog_path = root / "strategies" / "catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    catalog["strategyFiles"].append(f"strategies/generated/{strategy_id}.json")
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")


def test_bulk_remove_generated_presets_with_selection_fallback(tmp_path: Path) -> None:
    root = _project_copy(tmp_path)
    for index in (1, 2, 3):
        _write_generated(root, f"blockcheck-youtube-www-youtube-com-20261021-113000-0{index}")
    ids = [f"blockcheck-youtube-www-youtube-com-20261021-113000-0{index}" for index in (1, 2, 3)]
    assert all(can_remove_preset(load_preset(item, root)) for item in ids)
    assert not can_remove_preset(load_preset("community-discord-syndata-edge-flow-v2b", root))
    select_preset(ids[1], root=root)
    removed, errors = remove_presets([*ids, "community-discord-syndata-edge-flow-v2b"], root=root)
    assert [item.preset_id for item in removed] == ids
    assert len(errors) == 1 and "не создан конструктором" in errors[0]
    catalog = load_preset_catalog(root)
    assert not set(ids) & set(catalog.by_id())
    assert catalog.selected_preset_id == catalog.default_preset_id
    assert not list((root / "presets" / "generated").glob("blockcheck-*.txt"))
    assert not list((root / "strategies" / "generated").glob("blockcheck-*.json"))
    with pytest.raises(ValueError, match="не создан Blockcheck"):
        remove_generated_preset("manual-local", root)


def test_presets_page_bulk_deletes_selected_blockcheck_presets(tmp_path: Path, monkeypatch) -> None:
    pytest.importorskip("PyQt6")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PyQt6 import QtCore
    from PyQt6.QtWidgets import QApplication, QListWidget, QMessageBox, QPushButton

    from zap2_gui.widgets.presets import _chip_role, make_presets_page

    app = QApplication.instance() or QApplication([])
    root = _project_copy(tmp_path)
    ids = [f"blockcheck-youtube-www-youtube-com-20261021-113000-0{index}" for index in (1, 2)]
    for item in ids:
        _write_generated(root, item)
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *args, **kwargs: QMessageBox.StandardButton.Yes))
    settings = QtCore.QSettings(str(tmp_path / "settings.ini"), QtCore.QSettings.Format.IniFormat)
    page = make_presets_page(root, settings)
    (preset_list,) = [item for item in page.findChildren(QListWidget) if item.toolTip().startswith("Клик")]
    rows = {str(preset_list.item(i).data(QtCore.Qt.ItemDataRole.UserRole)): i for i in range(preset_list.count())}
    data = preset_list.item(rows[ids[0]]).data(_chip_role())
    assert data["title"].startswith("YouTube: multisplit · www.youtube.com")
    assert ("Blockcheck", "muted") in data["chips"]
    for item in (*ids, "community-discord-syndata-edge-flow-v2b"):
        preset_list.item(rows[item]).setSelected(True)
    app.processEvents()
    button = next(item for item in page.findChildren(QPushButton) if item.text().startswith("Удалить пресет"))
    assert button.text() == "Удалить пресеты: 2" and button.isEnabled()
    button.click()
    remaining = {str(preset_list.item(i).data(QtCore.Qt.ItemDataRole.UserRole)) for i in range(preset_list.count())}
    assert not set(ids) & remaining
    assert "community-discord-syndata-edge-flow-v2b" in remaining
    page.close()
