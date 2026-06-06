from zap2_gui.adapters.runtime_plan_generator import create_runtime_plan, runtime_plan_to_text
from zap2_gui.models.runtime_plan import validate_runtime_plan_contract


def test_runtime_plan_generator_builds_default_start_plan():
    plan = create_runtime_plan(action="start", profile_id="default")

    assert plan.action == "start"
    assert plan.profile.profile_id == "default"
    assert plan.strategy.strategy_id == "manual-local"
    assert plan.binary_relative_path == "core/zapret2/nfq2/nfqws2"
    assert [item.path for item in plan.hostlists] == ["profiles/hostlists/default.hosts"]
    assert plan.required_artifacts[0].relative_path == "nfq2/nfqws2"
    assert plan.requires_owner_confirmation is True
    assert plan.requires_sudo_for_apply is True
    assert plan.contract.lifecycle.automatic_checks_may_execute is False
    assert plan.contract.safety.contains_remote_bootstrap is False
    assert plan.contract.safety.contains_upstream_installer_script is False
    assert {section.kind for section in plan.contract.sections} == {"run", "apply", "session", "service"}
    assert not [issue for issue in validate_runtime_plan_contract(plan.contract) if issue.severity == "error"]


def test_runtime_plan_generator_builds_stop_and_status_plans():
    stop_plan = create_runtime_plan(action="stop", profile_id="default")
    status_plan = create_runtime_plan(action="status", profile_id="default")

    assert stop_plan.requires_sudo_for_apply is True
    assert status_plan.requires_sudo_for_apply is False
    assert status_plan.mutates_services_or_firewall is False
    assert "Status не имеет rollback" in "\n".join(status_plan.contract.rollback_notes)


def test_runtime_plan_generator_text_contains_required_fields():
    text = runtime_plan_to_text(action="start", profile_id="default")

    assert "Runtime plan для action: start" in text
    assert "profile: default" in text
    assert "strategy: manual-local" in text
    assert "build target: nfqws2" in text
    assert "binary: core/zapret2/nfq2/nfqws2" in text
    assert "profiles/hostlists/default.hosts" in text
    assert "required artifacts:" in text
    assert "session files:" in text
    assert "log files:" in text
    assert "apply steps:" in text
    assert "rollback steps:" in text
    assert "requires owner confirmation: yes" in text
    assert "requires sudo for apply: yes" in text
    assert "automatic checks may execute: no" in text
    assert "executes now: no" in text


def test_runtime_plan_generator_rejects_unknown_action():
    try:
        create_runtime_plan(action="unknown", profile_id="default")
    except ValueError as exc:
        assert "Неизвестное runtime action" in str(exc)
    else:
        raise AssertionError("unknown action must fail")
