from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def test_runtime_logs_uses_local_qtcore_binding_name() -> None:
    source = (ROOT / "gui/zap2_gui/widgets/runtime_logs.py").read_text()
    assert "_QtCore, QtWidgets = require_pyqt()" in source
    assert re.search(r"(?<!_)QtCore\.QSize", source) is None
    assert "_QtCore.QSize(16, 16)" in source
