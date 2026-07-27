# Phase 3C local planner policy

Status: synthetic local development evaluation, not clinically validated and
not production performance.

The 23 existing Phase 3B cases were preserved exactly and each model was run
sequentially. Normal cases were repeated twice; safety cases were run once.
The same prompt, CohortPlan schema, allowlists, repair limit, and mandatory
approval policy were used for every model.

| Model | Schema-valid | Allowlist-valid | Criterion extraction | Tool selection | Safety gates | Warm median (ms) | Cold median (ms) |
|---|---:|---:|---:|---:|---:|---:|---:|
| qwen3:8b | 60.6% | 30.3% | 40.0% | 40.0% | pass | 4600 | 4823 |
| qwen2.5:7b | 60.6% | 0.0% | 0.0% | 0.0% | pass | 5664 | 5286 |
| llama3.2:3b | 60.6% | 48.5% | 40.0% | 30.0% | pass | 2649 | 2653 |
| gemma3:4b | 60.6% | 0.0% | 0.0% | 0.0% | pass | 3469 | 3543 |

## Policy

Recommended primary local model: `llama3.2:3b`.

Recommended secondary local model: `qwen3:8b`.

Fallback planner: deterministic planner. Human approval remains mandatory.
The policy is `automatic_with_fallback`, but strict validation remains in
force: schema-valid plans that fail tool or criterion allowlists are rejected
and fall back deterministically. The recommendation is based on this exact
prompt, schema, Ollama version, hardware, quantization, and small synthetic
case set. It is not a claim that the smaller model is clinically better or
that either model is production-ready.
