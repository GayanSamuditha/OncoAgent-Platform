# Workflow policy

Phase 3B uses a localhost-only Ollama planner (`qwen3:8b`) when enabled and
falls back to the deterministic planner when it is unavailable or invalid.
All plans must validate against `CohortPlan`, use registered read-only tools,
remain dataset-scoped, respect the candidate limit, and require reviewer
approval. Development actor headers simulate identity and are not production
authentication. Planner scores and model outputs are not clinical decisions.

The global `AGENT_EXECUTION_ENABLED=false` kill switch prevents new execution.
Ollama is never exposed to the browser, never receives raw external data, and
never persists hidden reasoning.
