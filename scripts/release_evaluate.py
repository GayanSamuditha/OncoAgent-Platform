"""Run a deterministic, CLI-controlled release-candidate evaluation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))

from app.db.session import SessionLocal
from app.models.release_evaluation import (
    ReleaseCandidateRecord,
    ReleaseDecision,
    ReleaseEvaluationExecution,
    ReleaseGateResult,
    ReleaseMetricResult,
)
from app.release_evaluation.contracts import (
    ReleaseCandidate,
    ReleaseEvaluationReport,
)
from app.release_evaluation.service import (
    ROOT,
    evaluate_candidate,
    load_json,
    save_report,
    stable_hash,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", default="evaluations/release/phase6b_candidate.json")
    parser.add_argument("--baseline", default="evaluations/agents/phase4d_baseline_metrics.json")
    parser.add_argument("--suite", default="evaluations/release/phase6b_suite.json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    candidate_path = ROOT / args.candidate
    baseline_path = ROOT / args.baseline
    suite_path = ROOT / args.suite
    candidate = ReleaseCandidate.model_validate(load_json(candidate_path))
    suite = load_json(suite_path)
    if suite.get("suite_version") != candidate.evaluation_suite_version:
        raise SystemExit("candidate evaluation suite version does not match registry")
    candidate_data_path = ROOT / candidate.metrics_file if candidate.metrics_file else None
    candidate_data = (
        load_json(candidate_data_path)
        if candidate_data_path and candidate_data_path.exists()
        else {}
    )
    baseline_data = load_json(baseline_path) if baseline_path.exists() else None
    baseline_reference = {
        "path": args.baseline,
        "version": baseline_data.get("version") if baseline_data else None,
        "available": baseline_data is not None,
    }
    report = evaluate_candidate(
        candidate,
        candidate_data,
        baseline_data,
        baseline_reference=baseline_reference,
        scenario_definition_hash=stable_hash(suite),
    )
    save_report(report)
    with SessionLocal.begin() as session:
        existing = (
            session.query(ReleaseCandidateRecord)
            .filter(
                ReleaseCandidateRecord.candidate_id == candidate.candidate_id,
                ReleaseCandidateRecord.candidate_version == candidate.candidate_version,
            )
            .one_or_none()
        )
        if existing is None:
            existing = ReleaseCandidateRecord(
                id=str(uuid4()),
                candidate_id=candidate.candidate_id,
                candidate_version=candidate.candidate_version,
                baseline_id=candidate.baseline_id,
                baseline_version=candidate.baseline_version,
                dataset_id=candidate.dataset_id,
                evaluation_suite_version=candidate.evaluation_suite_version,
                artifact_versions=report.artifact_versions,
                manifest=candidate.model_dump(mode="json"),
            )
            session.add(existing)
            session.flush()
        duplicate = (
            session.query(ReleaseEvaluationExecution)
            .filter(
                ReleaseEvaluationExecution.candidate_id == existing.id,
                ReleaseEvaluationExecution.evaluation_input_hash == report.evaluation_input_hash,
            )
            .one_or_none()
        )
        if duplicate is not None:
            report = ReleaseEvaluationReport.model_validate(duplicate.report_json)
        else:
            execution = ReleaseEvaluationExecution(
                id=report.evaluation_id,
                candidate_id=existing.id,
                decision=report.decision,
                report_version=report.report_version,
                evaluation_input_hash=report.evaluation_input_hash,
                baseline_reference=report.baseline_reference,
                framework_results=report.framework_results,
                limitations=report.limitations,
                report_json=report.model_dump(mode="json"),
            )
            session.add(execution)
            session.flush()
            session.add_all(
                [
                    ReleaseMetricResult(
                        id=str(uuid4()),
                        evaluation_id=report.evaluation_id,
                        metric_name=item.name,
                        value=item.value,
                        baseline_value=item.baseline_value,
                        status=item.status,
                        sample_size=item.sample_size,
                        denominator=item.denominator,
                        definition=item.definition,
                        direction=item.direction,
                        delta=item.delta,
                    )
                    for item in report.metrics
                ]
            )
            session.add_all(
                [
                    ReleaseGateResult(
                        id=str(uuid4()),
                        evaluation_id=report.evaluation_id,
                        gate_name=item.name,
                        metric_name=item.metric_name,
                        value=item.value,
                        threshold=item.threshold,
                        status=item.status,
                        passed=item.passed,
                        blocking=item.blocking,
                        sample_size=item.sample_size,
                        reason=item.reason,
                    )
                    for item in report.gates
                ]
            )
            session.add(
                ReleaseDecision(
                    id=str(uuid4()),
                    evaluation_id=report.evaluation_id,
                    decision=report.decision,
                    blocking_reasons=report.blocking_reasons,
                )
            )
    print(
        json.dumps(
            {
                "evaluation_id": report.evaluation_id,
                "decision": report.decision,
                "blocking_reasons": report.blocking_reasons,
                "report": f"evaluation_outputs/release/{report.evaluation_id}.json",
            },
            indent=2,
        )
    )
    return 0 if report.decision != "blocked" else 1


if __name__ == "__main__":
    raise SystemExit(main())
