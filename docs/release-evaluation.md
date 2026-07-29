# Phase 6B release evaluation

Release evaluation is a CLI-controlled, versioned development gate for
candidate changes to models, prompts, retrieval, workflows, MCP tools,
governance, safety, and identity policy. It compares a candidate manifest with
an explicitly selected baseline and a source-controlled evaluation suite.

The runner is `scripts/release_evaluate.py` and the convenience targets are:

```text
make release-evaluate
make release-evaluate CANDIDATE=evaluations/release/phase6b_candidate.json
make release-report
```

Candidate measurements must be supplied by an evaluation worker in an ignored
`evaluation_outputs/release/` artifact. Missing measurements are represented
as `not_evaluable` and fail required gates; the runner never infers a pass.
An explicitly declared metric with no applicable scenarios is represented as
`not_applicable`; it remains visible and does not block unrelated applicable
gates. The distinction is part of the persisted report contract.
Generated JSON and Markdown reports are ignored and contain only sanitized
metrics and lineage metadata.

## Versioned inputs

`evaluations/release/phase6b_suite.json` identifies the suite and its unchanged
scenario source. `phase6b_candidate.json` records framework, model, prompt,
retrieval, workflow, MCP registry, governance taxonomy, resilience registry,
identity policy, dataset, and baseline versions. The report records an input
hash so the decision is reproducible.

## Gates and decisions

Blocking gates cover unsafe execution, policy prevention, human review,
required-criterion provenance for included patients, applicable lifecycle
audit, orphan MCP requests, duplicate business records, policy-denial retry,
cancellation finalization, authorization bypass, self-approval, and telemetry
redaction. Overall evidence coverage is reported separately and is not a
blocking gate because missing or unverified evidence must remain visible.

Decisions are `approved`, `blocked`, or
`approved_with_documented_limitations`. A missing baseline is reported rather
than silently substituted. Repeating the same candidate version and input hash
is idempotent in the application records; historical candidates remain
inspectable through the read APIs.

## API and frontend

Authenticated readers with `evaluation:read` may use:

- `GET /api/v1/release-evaluations`
- `GET /api/v1/release-evaluations/{evaluation_id}`
- `GET /api/v1/release-evaluations/{evaluation_id}/gates`
- `GET /api/v1/release-evaluations/{evaluation_id}/metrics`

The Release Gates page displays actual persisted reports, gate status, metric
deltas, framework results, and limitations. It cannot execute an evaluation.

This is synthetic local development evaluation only. It is not clinically
validated, not a regulatory certification, and not production performance.
