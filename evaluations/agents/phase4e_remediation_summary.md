# Phase 4E remediation result

Synthetic development evaluation only; not clinically validated, a
regulatory certification, or production performance. The unchanged 16
scenarios were rerun with the same scenario hash as the prior evaluation.

## Root causes

- LangGraph provenance gate: a real persistence defect and a converter
  mapping defect. `workflow_candidates.included` was never updated after
  structured verification, and the evaluator compared persisted criterion
  IDs with client criterion types. Candidate verification now updates the
  persisted flags, and normalization uses the persisted criterion IDs.
- CrewAI provenance gate: successful fallback briefs did not expose a
  normalized included-patient denominator. The validator now treats empty
  included sets correctly and preserves MCP/source identifiers for any
  proposed inclusion.
- CrewAI audit gate: successful lifecycle events existed, but the evaluator
  counted pre-execution HTTP rejections as missing audit runs. Applicable
  lifecycle runs are now measured separately; request-to-task context is
  persisted and reconciled against MCP audit rows.
- An additional runtime defect was found during remediation: detached
  SQLAlchemy task/agent instances were reused across transactions. IDs are
  now copied before the transaction closes.

## Results

| Framework | Outcome match | Included required provenance | Overall provenance | Lifecycle audit | MCP correlation | Orphans | Safe handling |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| LangGraph Phase 4C | 68.75% | not separately measured | 35.33% | 100% | not measured | not measured | not measured |
| CrewAI Phase 4C | 87.50% | not separately measured | 68.75% | 68.75% | not measured | not measured | not measured |
| LangGraph Phase 4D | 68.75% | 35.33% | 35.33% | 100% | not measured | not measured | 100% |
| CrewAI Phase 4D | 87.50% | 68.75% | 68.75% | 68.75% | not measured | not measured | 100% |
| LangGraph Phase 4E | 68.75% | 100% | 66.58% | 100% | 100% | 0% | 100% |
| CrewAI Phase 4E | 87.50% | 100% | 68.75% | 100% | 100% | 0% | 100% |

The overall provenance metric remains below 100% because it includes all
persisted evidence rows, including not-verified and missing-data rows. The
required included-patient metric passes because every included required
criterion has a source FHIR identifier. No provenance was fabricated.

All Phase 4E governance gates pass. The result is development-ready for
continued synthetic testing, not production-ready or clinically validated.
