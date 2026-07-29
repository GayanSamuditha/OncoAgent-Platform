from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Decision = Literal["approved", "blocked", "approved_with_documented_limitations"]
MetricStatus = Literal["measured", "not_evaluable", "not_applicable"]


class ReleaseCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str = Field(min_length=1, max_length=120)
    candidate_version: str = Field(min_length=1, max_length=80)
    baseline_id: str | None = None
    baseline_version: str | None = None
    dataset_id: str
    framework_versions: dict[str, str] = Field(default_factory=dict)
    model_versions: dict[str, str] = Field(default_factory=dict)
    model_digests: dict[str, str] = Field(default_factory=dict)
    prompt_versions: dict[str, str] = Field(default_factory=dict)
    retrieval_profiles: list[str] = Field(default_factory=list)
    workflow_version: str | None = None
    mcp_tool_registry_version: str | None = None
    governance_taxonomy_version: str | None = None
    resilience_registry_version: str | None = None
    identity_policy_version: str | None = None
    evaluation_suite_version: str
    metrics_file: str | None = None
    limitations: list[str] = Field(default_factory=list)


class MetricResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    value: float | None = None
    status: MetricStatus
    applicable: bool = True
    sample_size: int = Field(ge=0)
    denominator: int | None = Field(default=None, ge=0)
    definition: str
    direction: Literal["higher", "lower", "none"] = "none"
    baseline_value: float | None = None
    delta: float | None = None
    limitations: list[str] = Field(default_factory=list)


class GateResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    metric_name: str
    value: float | None = None
    threshold: float
    passed: bool
    status: Literal["passed", "failed", "not_evaluable", "not_applicable"]
    blocking: bool = True
    sample_size: int = Field(ge=0)
    definition: str
    reason: str


class ReleaseEvaluationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evaluation_id: str
    report_version: str
    candidate: ReleaseCandidate
    baseline_reference: dict[str, Any]
    evaluation_input_hash: str
    scenario_definition_hash: str | None = None
    metrics: list[MetricResult]
    gates: list[GateResult]
    regressions: list[str] = Field(default_factory=list)
    decision: Decision
    blocking_reasons: list[str] = Field(default_factory=list)
    framework_results: dict[str, Any] = Field(default_factory=dict)
    artifact_versions: dict[str, str] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)
    synthetic_development_evaluation: bool = True
    not_clinically_validated: bool = True
    not_production_performance: bool = True


def metric_lookup(metrics: list[MetricResult]) -> dict[str, MetricResult]:
    return {item.name: item for item in metrics}
