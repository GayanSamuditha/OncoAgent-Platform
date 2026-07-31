import pytest
from pydantic import ValidationError

from app.performance.contracts import HardwareProfile, WorkloadProfile


def test_workload_contract_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        WorkloadProfile(
            profile_id="x",
            description="x",
            concurrency=1,
            request_count=1,
            warmup_count=0,
            timeout_seconds=1,
            max_memory_gb=1,
            unbounded=True,
        )


def test_hardware_profile_has_explicit_context() -> None:
    profile = HardwareProfile(platform="Darwin", architecture="arm64", cpu_count=8, memory_gb=24)
    assert profile.docker_configuration == "local-development"
