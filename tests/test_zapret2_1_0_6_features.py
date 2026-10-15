from __future__ import annotations

import json
from pathlib import Path

import pytest

from zap2_gui.adapters.blockcheck_gui import (
    BlockcheckOptions,
    BlockcheckCoverageRow,
    blockcheck_coverage_json_path,
    parse_blockcheck_coverage,
)
from zap2_gui.adapters.preset_editor import validate_filter_mark, validate_new_filter_args
from zap2_gui.adapters.preset_editor import EditableTrafficProfile

FIXTURE = Path(__file__).parent / "fixtures" / "blockcheck2_1_0_6_coverage_sample.txt"


def test_parse_coverage_section_from_fixture():
    rows = parse_blockcheck_coverage(FIXTURE.read_text(encoding="utf-8"))
    assert rows == (
        BlockcheckCoverageRow(
            "curl_test_https_tls12 ipv4 : nfqws2 --payload=tls_client_hello --lua-desync=multisplit:pos=1", 2, 2
        ),
        BlockcheckCoverageRow(
            "curl_test_https_tls12 ipv4 : nfqws2 --payload=tls_client_hello --lua-desync=fake:blob=fake_default_tls:tcp_md5",
            1,
            2,
        ),
    )
    assert rows[1].to_dict()["worked"] == 1


def test_coverage_absent_for_single_domain_output():
    assert parse_blockcheck_coverage("* SUMMARY\nipv4 a.org x : nfqws2 --x\n") == ()


def test_coverage_json_sidecar_name():
    assert blockcheck_coverage_json_path(Path("/x/last-blockcheck.txt")).name == "last-blockcheck-coverage.json"
    json.dumps([r.to_dict() for r in parse_blockcheck_coverage(FIXTURE.read_text())])


def test_curl_pad_env_off_by_default_and_passed_when_set():
    assert "CURL_PAD" not in BlockcheckOptions(domains="example.org").to_env()
    options = BlockcheckOptions(domains="example.org", curl_pad=20000)
    assert options.to_env()["CURL_PAD"] == "20000"
    assert options.for_single_domain("example.org").curl_pad == 20000


@pytest.mark.parametrize("value", [-1, 10, 70000])
def test_curl_pad_bounds(value):
    with pytest.raises(ValueError, match="CURL_PAD"):
        BlockcheckOptions(domains="example.org", curl_pad=value).validate()


@pytest.mark.parametrize(
    "value,expected",
    [("0x10", (0x10, 0xFFFFFFFF)), ("16/0xF0", (16, 0xF0)), ("0x40000000/0x40000000", (0x40000000, 0x40000000)), ("4294967295", (0xFFFFFFFF, 0xFFFFFFFF))],
)
def test_filter_mark_valid(value, expected):
    assert validate_filter_mark(value) == expected


@pytest.mark.parametrize("value", ["", "abc", "0x", "4294967296", "0x1/0", "0x10/0x0F", "-1", "1/2/3", "0x123456789"])
def test_filter_mark_invalid(value):
    with pytest.raises(ValueError):
        validate_filter_mark(value)


def test_filter_args_ssid_negation():
    assert validate_new_filter_args(["--filter-ssid=home", "--filter-ssid-neg"]) == ()
    assert validate_new_filter_args(["--filter-ssid=home", "--filter-ssid-neg=1", "--filter-mark=0x10/0x10"]) == ()
    assert validate_new_filter_args(["--filter-ssid=home", "--filter-ssid-neg=2"])
    assert validate_new_filter_args(["--filter-ssid-neg", "--new", "--filter-ssid=x"])
    assert validate_new_filter_args(["--ssid-filter-neg=1"])
    assert validate_new_filter_args(["--filter-mark"])


def test_editable_profile_emits_filter_mark():
    profile = EditableTrafficProfile(
        name="marked", protocol="tcp", ports="443", filter_mark="0x10/0xF0",
        strategy_args=("--lua-desync=multisplit:pos=1",),
    )
    assert "--filter-mark=0x10/0xF0" in profile.to_raw_args()
    with pytest.raises(ValueError):
        EditableTrafficProfile(
            name="bad", protocol="tcp", ports="443", filter_mark="0xZZ",
            strategy_args=("--lua-desync=multisplit:pos=1",),
        ).validate()
