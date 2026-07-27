# Phase 4B CrewAI runtime evaluation

This is a synthetic development evaluation on local hardware. It is not
clinically validated and is not evidence of production performance. Results
are specific to the prompts, schemas, CrewAI version, MCP gateway, Ollama
runtime, `llama3.2:3b` quantization, and the `synthea-eval-100` development
dataset.

## Evaluation definition

The source-controlled suite contains 17 scenarios covering condition,
combined condition/observation, procedure, medication, encounter type, age,
date windows, missing/conflicting/no-result evidence, ambiguity, and five
unsafe-request classes. Ground truth is expressed in
[`phase4b_cases.json`](phase4b_cases.json); clinical evidence is expected to
come from structured MCP responses with FHIR resource provenance.

## llama3.2:3b result

The real sequential run produced 17 records. Ten clinical scenarios reached
`awaiting_human_review`; seven scenarios were rejected safely. All five
adversarial scenarios returned HTTP 422 before tool execution. The measured
end-to-end median was 4,627 ms and p95 was 4,649 ms for this bounded local
run. The ignored machine-readable record is
`evaluation_outputs/crewai/phase4b_llama.json`.

The run also validated MCP-only execution for successful clinical cases,
structured review envelopes, reviewer closure, and process interruption
recovery. One malformed date-window definition was rejected by Pydantic during
the first run; the source definition was corrected to use explicit ISO date
bounds and must be rerun before treating that case as a successful clinical
scenario.

## qwen3:8b comparison

The requested four-case comparison was started sequentially. The first
condition-plus-observation case reached human review. The next qwen run
exceeded the bounded local execution window and was interrupted; its persisted
run was marked `failed` with `process_interrupted` after API restart. No
four-case aggregate is reported because the sample is incomplete. This is a
runtime limitation, not a fabricated metric or a model-selection claim.

## Safety and durability findings

- Prompt-injection, direct-database, MCP-bypass, approval-bypass, and raw-FHIR
  export requests were rejected with no clinical MCP calls.
- Human review remains mandatory; a CrewAI run never accepts or finalizes its
  own result.
- MCP request IDs and CrewAI run IDs are persisted separately and correlated
  through lineage records.
- Local autonomous execution is not durable across process failure. Persisted
  run/task/audit records remain inspectable, but an in-flight model call is
  marked failed and is never resumed automatically. A process-isolated worker
  keeps FastAPI health and inspection endpoints responsive.

## Reproduction

```bash
python scripts/evaluate_crewai.py \
  --base-url http://127.0.0.1:8001 \
  --model llama3.2:3b \
  --evaluation-file evaluations/crewai/phase4b_cases.json \
  --output evaluation_outputs/crewai/phase4b_llama.json
```

Generated results remain ignored. Do not copy local model output, tokens,
raw FHIR, or database artifacts into source control.
