import os
import shlex

import pytest

from zap2_gui.adapters.runtime_session import _nfqws_args_file_text, _public_session_inputs_base


def test_nfqws_args_file_quotes_shell_sensitive_out_ranges() -> None:
    text = _nfqws_args_file_text((
        "--filter-tcp=443",
        "--out-range=<s1",
        "--out-range=s1<d1",
        "--lua-desync=syndata:blob=fake_default_tls:tls_mod=rnd,dupsid,rndsni",
    ))

    assert "'--out-range=<s1'" in text
    assert "'--out-range=s1<d1'" in text
    parsed = shlex.split("x " + text.replace("\n", " "))[1:]
    assert parsed == [
        "--filter-tcp=443",
        "--out-range=<s1",
        "--out-range=s1<d1",
        "--lua-desync=syndata:blob=fake_default_tls:tls_mod=rnd,dupsid,rndsni",
    ]


def test_nfqws_args_file_quotes_paths_with_spaces() -> None:
    text = _nfqws_args_file_text((
        "--pidfile=/tmp/zap2 test/default.nfqws2.pid",
        "--lua-init=@/tmp/zap2 test/lua/zapret-lib.lua",
    ))

    assert "'--pidfile=/tmp/zap2 test/default.nfqws2.pid'" in text
    assert "'--lua-init=@/tmp/zap2 test/lua/zapret-lib.lua'" in text
    parsed = shlex.split("x " + text.replace("\n", " "))[1:]
    assert parsed == [
        "--pidfile=/tmp/zap2 test/default.nfqws2.pid",
        "--lua-init=@/tmp/zap2 test/lua/zapret-lib.lua",
    ]


def test_nfqws_args_file_rejects_newline_in_arg() -> None:
    with pytest.raises(ValueError, match="NUL/newline"):
        _nfqws_args_file_text(("--filter-tcp=443\n--new",))


def test_default_public_runtime_inputs_base_is_uid_scoped(monkeypatch) -> None:
    monkeypatch.delenv("ZAP2_PUBLIC_RUNTIME_INPUTS_DIR", raising=False)

    base = _public_session_inputs_base()

    assert base.name == f"zap2-runtime-inputs-{os.getuid()}"


def test_configured_public_runtime_inputs_base_preserves_legacy_layout(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ZAP2_PUBLIC_RUNTIME_INPUTS_DIR", str(tmp_path / "public-runtime"))

    base = _public_session_inputs_base()

    assert base == tmp_path / "public-runtime" / "zap2-runtime-inputs"
