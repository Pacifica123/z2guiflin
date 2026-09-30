from __future__ import annotations

from pathlib import Path

from zap2_gui import PRODUCT_LABEL, __version__


ROOT = Path(__file__).resolve().parents[1]


def test_product_version_tracks_accepted_v08_after_p04_closure() -> None:
    assert PRODUCT_LABEL == "v1.1"
    assert __version__ == "1.1.0"

    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'version = "1.1.0"' in pyproject
    assert 'version = "0.4.0a0"' not in pyproject


def test_current_docs_define_environment_dependent_release_boundary() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    release = (ROOT / "docs" / "history" / "stages" / "V04_RELEASE.md").read_text(encoding="utf-8")
    status = (ROOT / "docs" / "PROJECT_STATUS.md").read_text(encoding="utf-8")

    assert "Zap2 GUI Linux — v1.1" in readme
    assert "не универсальную стратегию" in readme
    assert "не обещает" in readme
    assert "рабочая платформа" in release
    assert "зависит не только от проекта" in release
    assert "0.8.0" in status
    assert "P04 закрыт" in status
    assert "P04a" in status
    assert "P04b" in status
    assert "P04c" in status
    assert "P04d" in status
    assert "READY_FOR_USE_WITHIN_P04D" in status
    assert "P05" in status


def test_horizontal_gap_checklists_cover_reference_projects() -> None:
    text = (ROOT / "docs" / "history" / "stages" / "KNOWN_GAPS_CHECKLISTS.md").read_text(encoding="utf-8")

    for marker in ("bol-van", "loop-uh", "Flowseal", "Категоризация горизонтальная"):
        assert marker in text

    for category in (
        "Установка, зависимости и обновление",
        "Runtime, firewall и жизненный цикл процессов",
        "Пресеты, профили и композиция",
        "Blockcheck и подбор стратегий",
        "HAR и обнаружение целей",
        "Discord Voice, UDP и игровые диапазоны",
        "Proxy, VLESS и VPN",
        "GUI и повседневный UX",
        "Тестирование и качество релиза",
    ):
        assert category in text

    assert text.count("- [ ]") >= 25
    assert text.count("- [~]") >= 10
    assert text.count("- [x]") >= 10


def test_documentation_index_and_audit_exist() -> None:
    index = (ROOT / "docs" / "README.md").read_text(encoding="utf-8")
    audit = (ROOT / "docs" / "history" / "stages" / "DOCUMENTATION_AUDIT.md").read_text(encoding="utf-8")

    assert "Сначала читать" in index
    assert "История исследований v0.4" in audit
    assert "Vendored upstream" in audit
