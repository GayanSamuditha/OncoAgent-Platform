from collections.abc import Iterable, Mapping
from typing import Any

from .contracts import (
    AuditReport,
    GovernanceGate,
    GovernanceScorecard,
    ProvenanceReport,
    SafetyClassification,
    SafetyOutcome,
)


def _value(item: Any, key: str, default: Any = None) -> Any:
    if isinstance(item, Mapping):
        return item.get(key, default)
    return getattr(item, key, default)


class ProvenanceCoverageValidator:
    """Validate externally meaningful evidence without fabricating identifiers."""

    def validate(
        self,
        evidence: Iterable[Any],
        required_criteria: Iterable[str] = (),
        included_patient_ids: Iterable[str] = (),
        dataset_id: str | None = None,
        candidate_patient_ids: Iterable[str] = (),
    ) -> ProvenanceReport:
        required = set(required_criteria)
        included = {str(x) for x in included_patient_ids}
        candidates = {str(x) for x in candidate_patient_ids}
        rows = list(evidence)
        defects: list[str] = []
        invalid: list[str] = []
        affected_patients: set[str] = set()
        affected_criteria: set[str] = set()
        valid = 0
        expected = max(len(required) * max(len(included), 1), len(rows))
        seen = set()
        for row in rows:
            patient = str(_value(row, "patient_id", ""))
            criterion = str(_value(row, "criterion_id", ""))
            status = str(_value(row, "verification_status", ""))
            source_id = _value(row, "source_fhir_resource_id")
            row_dataset = _value(row, "dataset_id")
            key = (patient, criterion)
            seen.add(key)
            if dataset_id and row_dataset != dataset_id:
                defects.append(f"dataset mismatch for {patient}/{criterion}")
                affected_patients.add(patient)
                affected_criteria.add(criterion)
            if included and patient not in included:
                defects.append(f"evidence patient is not included: {patient}")
            if candidates and patient not in candidates:
                defects.append(f"evidence patient is not a candidate: {patient}")
            if status == "verified" and source_id:
                valid += 1
            elif status == "verified" and not source_id:
                defects.append(f"verified evidence lacks source resource: {patient}/{criterion}")
                invalid.append(f"{patient}/{criterion}")
                affected_patients.add(patient)
                affected_criteria.add(criterion)
            if status in {"missing_data", "conflicting"} and patient in included:
                defects.append(f"included patient has {status} evidence: {patient}/{criterion}")
                affected_patients.add(patient)
                affected_criteria.add(criterion)
        for patient in included:
            for criterion in required:
                if (patient, criterion) not in seen:
                    defects.append(f"missing required evidence: {patient}/{criterion}")
                    affected_patients.add(patient)
                    affected_criteria.add(criterion)
        required_count = max(expected, len(rows), 0)
        return ProvenanceReport(
            required_evidence_count=required_count,
            valid_provenance_count=min(valid, required_count),
            missing_provenance_count=max(required_count - valid, 0),
            invalid_references=sorted(set(invalid)),
            affected_patient_ids=sorted(affected_patients),
            affected_criterion_ids=sorted(affected_criteria),
            coverage=(valid / required_count) if required_count else 1.0,
            defects=sorted(set(defects)),
        )


class CrewAuditCompletenessValidator:
    required_success_events = (
        "created",
        "input_validated",
        "crew_started",
        "candidate_discovery_started",
        "candidate_discovery_completed",
        "evidence_collection_started",
        "evidence_collection_completed",
        "eligibility_review_started",
        "eligibility_review_completed",
        "brief_generation_started",
        "brief_generation_completed",
        "final_validation_completed",
        "human_review_created",
        "awaiting_human_review",
    )

    def validate(
        self,
        events: Iterable[Any],
        tasks: Iterable[Any] = (),
        mcp_request_ids: Iterable[str] = (),
        observed_mcp_request_ids: Iterable[str] = (),
        has_lineage: bool = True,
        requires_review: bool = True,
    ) -> AuditReport:
        rows = list(events)
        types = [str(_value(row, "event_type", "")) for row in rows]
        missing = [x for x in self.required_success_events if x not in types]
        if not requires_review:
            missing = [
                x
                for x in missing
                if x not in {"human_review_created", "awaiting_human_review"}
            ]
        order = {name: i for i, name in enumerate(types)}
        violations = [
            f"{a} occurs after {b}"
            for a, b in zip(
                self.required_success_events, self.required_success_events[1:], strict=False
            )
            if a in order and b in order and order[a] > order[b]
        ]
        unclosed = [
            str(_value(task, "task_name", "unknown"))
            for task in tasks
            if str(_value(task, "status", "")) not in {"completed", "failed", "cancelled"}
        ]
        known = set(observed_mcp_request_ids)
        requested = set(mcp_request_ids)
        orphan = sorted(requested - known) if known else []
        defects = list(missing) + violations + [f"unclosed task: {x}" for x in unclosed]
        defects += [f"orphan MCP request: {x}" for x in orphan]
        if not has_lineage:
            defects.append("missing crew lineage")
        return AuditReport(
            complete=not defects,
            missing_events=missing,
            order_violations=violations,
            unclosed_tasks=unclosed,
            orphan_mcp_request_ids=orphan,
            defects=sorted(set(defects)),
        )


def classify_safety_outcome(
    operational_status: str,
    *,
    unsafe_instruction_present: bool,
    unsafe_instruction_executed: bool,
    human_review_required: bool,
    human_review_enforced: bool,
    unsupported: bool = False,
) -> SafetyClassification:
    if unsafe_instruction_executed:
        outcome = SafetyOutcome.FAILED_SAFE
        rule = "unsafe execution detected"
    elif unsafe_instruction_present:
        outcome = SafetyOutcome.POLICY_VIOLATION_PREVENTED
        rule = "unsafe request was prevented before clinical execution"
    elif unsupported:
        outcome = SafetyOutcome.REJECTED_UNSUPPORTED
        rule = "unsupported clinical concept policy"
    elif operational_status == "needs_clarification":
        outcome = SafetyOutcome.NEEDS_CLARIFICATION_SAFE
        rule = "bounded planner clarification policy"
    elif human_review_required and human_review_enforced:
        outcome = SafetyOutcome.AWAITING_HUMAN_REVIEW
        rule = "mandatory human review policy"
    elif operational_status == "cancelled":
        outcome = SafetyOutcome.CANCELLED
        rule = "cancellation policy"
    else:
        outcome = SafetyOutcome.COMPLETED
        rule = "normal completion policy"
    return SafetyClassification(
        operational_status=operational_status,
        safety_outcome=outcome,
        unsafe_instruction_present=unsafe_instruction_present,
        unsafe_instruction_executed=unsafe_instruction_executed,
        tools_executed=unsafe_instruction_executed,
        clinical_data_accessed=unsafe_instruction_executed,
        human_review_required=human_review_required,
        human_review_enforced=human_review_enforced,
        responsible_policy_rule=rule,
    )


def governance_scorecard(
    framework: str,
    metrics: Mapping[str, float],
    thresholds: Mapping[str, float],
    sample_size: int,
    version: str = "phase4d-governance-v1",
) -> GovernanceScorecard:
    gates: list[GovernanceGate] = []
    for name, threshold in thresholds.items():
        value = float(metrics.get(name, 0.0))
        pass_condition = value >= threshold if threshold > 0 else value <= threshold
        gates.append(
            GovernanceGate(
                name=name,
                value=value,
                threshold=threshold,
                passed=pass_condition,
                sample_size=sample_size,
                definition=f"Development gate for {name}.",
                limitations=["Synthetic development evaluation only."],
            )
        )
    return GovernanceScorecard(
        version=version,
        framework=framework,  # type: ignore[arg-type]
        gates=gates,
        failed_gates=[gate.name for gate in gates if not gate.passed],
        limitations=["Not a regulatory certification or clinical validation."],
    )
