from app.core.config import Settings
from app.temporal.fault_injection import configured_fault


def test_development_fault_is_allowlisted_and_one_shot() -> None:
    settings = Settings(
        environment="local",
        temporal_dev_fault_stage="execute_crewai_pipeline",
        temporal_dev_fault_category="mcp_transport_failure",
        temporal_dev_fault_attempts=1,
    )
    assert configured_fault(settings, "execute_crewai_pipeline", 1) == "mcp_transport_failure"
    assert configured_fault(settings, "execute_crewai_pipeline", 2) is None


def test_fault_injection_is_disabled_outside_local_test() -> None:
    settings = Settings(
        environment="production",
        temporal_dev_fault_stage="execute_crewai_pipeline",
        temporal_dev_fault_category="ollama_unavailable",
    )
    assert configured_fault(settings, "execute_crewai_pipeline", 1) is None


def test_fault_injection_rejects_unknown_categories() -> None:
    settings = Settings(
        environment="local",
        temporal_dev_fault_stage="execute_crewai_pipeline",
        temporal_dev_fault_category="arbitrary_code",
    )
    assert configured_fault(settings, "execute_crewai_pipeline", 1) is None
