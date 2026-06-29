from __future__ import annotations

from pathlib import Path

from zap2_gui.adapters.launch_error_classifier import classify_launch_issue


def test_classifier_detects_xhttp_core_error() -> None:
    issue = classify_launch_issue(
        action="Combined toggle start",
        text="last core stderr: unknown transport protocol: xhttp",
        selected_status="Zapret default: running/ready; VLESS tunnel: stopped/ready",
        all_selected_running=False,
    )

    assert issue is not None
    assert issue.code == "Z2-TUNNEL-XHTTP-CORE"
    assert "xhttp" in issue.message
    assert "Z2-TUNNEL-XHTTP-CORE" in issue.short_text()
    assert "last core stderr" in issue.full_text()


def test_classifier_detects_partial_combined_start() -> None:
    issue = classify_launch_issue(
        action="Combined toggle start",
        text="Final status",
        selected_status="Zapret default: running/ready; VLESS tunnel: stopped/ready",
        all_selected_running=False,
    )

    assert issue is not None
    assert issue.code == "Z2-LAUNCH-PARTIAL"
    assert "Не все выбранные компоненты" in issue.message


def test_classifier_ignores_successful_combined_start() -> None:
    issue = classify_launch_issue(
        action="Combined toggle start",
        text="Final status",
        selected_status="Zapret default: running/ready; VLESS tunnel: running/ready",
        all_selected_running=True,
    )

    assert issue is None


def test_overview_banner_ui_contract_is_present() -> None:
    source = (Path(__file__).resolve().parents[1] / "gui/zap2_gui/widgets/runtime_controls.py").read_text()

    assert 'launch_issue_banner.setObjectName("launchIssueBanner")' in source
    assert 'copy_issue_short_button = QtWidgets.QPushButton(misc_icon("copy"), "")' in source
    assert 'copy_issue_full_button = QtWidgets.QPushButton(misc_icon("details"), "")' in source
    assert 'close_issue_button = QtWidgets.QPushButton("×")' in source
    assert "show_launch_issue(issue)" in source
    assert "classify_launch_issue(" in source
