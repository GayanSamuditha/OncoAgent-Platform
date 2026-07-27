from app.workflow.policy_selection import safety_gate, select_policy


def test_safety_gate_is_mandatory() -> None:
    assert safety_gate({"unsupported_request_safety_rate": 1, "prompt_injection_resistance_rate": 1, "approval_bypass_resistance_rate": 1})
    assert not safety_gate({"unsupported_request_safety_rate": 1, "prompt_injection_resistance_rate": 0.99, "approval_bypass_resistance_rate": 1})


def test_policy_selects_quality_winner_only_after_safety_gate() -> None:
    policy = select_policy({
        "qwen3:8b": {"unsupported_request_safety_rate": 1, "prompt_injection_resistance_rate": 1, "approval_bypass_resistance_rate": 1, "allowlist_valid_rate": 0.5},
        "llama3.2:3b": {"unsupported_request_safety_rate": 1, "prompt_injection_resistance_rate": 1, "approval_bypass_resistance_rate": 0, "allowlist_valid_rate": 1},
    })
    assert policy["primary_local_model"] == "qwen3:8b"
    assert policy["fallback_planner"] == "deterministic"
    assert policy["human_approval_required"] is True


def test_policy_uses_deterministic_mode_when_no_model_passes() -> None:
    policy = select_policy({"qwen3:8b": {"unsupported_request_safety_rate": 0}}, baseline="qwen3:8b")
    assert policy["mode"] == "deterministic_safety_fallback"
    assert policy["safety_gate_passed"] is False
