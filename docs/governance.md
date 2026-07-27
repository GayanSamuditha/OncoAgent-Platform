# Governance Controls

## Data

Only synthetic Synthea data is permitted. Archives, extracted FHIR files, generated patient records, embeddings, and database volumes are local or external artifacts and must remain outside Git. Phase 1 stores raw FHIR JSON only for a bounded selected sample, with archive/member provenance. The platform must remain clearly labeled as not clinically validated.

## Traceability

Dataset and ingestion runs record archive identity, sample policy, requested limit, counts, status, and failure information. Raw resources retain source archive name, member path, and member hash. Future workflow runs must additionally record agent/node, prompt version, model version, tool schema/version, evidence references, and human decisions.

## Secrets and access

Credentials are supplied through environment variables. `.env` files, tokens, and production credentials are forbidden in source control. Future roles will separate researchers, reviewers, and administrators, with least-privilege database access.

## Dependency and model risk

Dependencies require a present implementation need. Deferred agent, orchestration, and deployment frameworks must not be installed early. Future model evaluations must use documented synthetic fixtures and must not be presented as clinical performance.

## Retrieval evaluation

Hybrid fusion and cross-encoder reranking are evaluated on the same bounded dataset and structured-ground-truth cases. RRF constants, candidate-pool sizes, model revisions, latency, negative results, and failure analysis are recorded. Similarity and reranker logits are ranking signals, not clinical probabilities. Profile selection is policy-controlled and must consider quality, latency, memory, complexity, and failure characteristics.

## Phase 3A workflow governance

Workflow state is checkpointed in PostgreSQL by LangGraph and mirrored into application events, steps, tool calls, policy decisions, evidence, approval, and lineage tables. Only registered read-only tools may execute. Plans are Pydantic-validated and dataset-scoped. Inclusion requires every required criterion to be verified from normalized structured FHIR facts with provenance. Approval records are idempotent and finalization is terminal-state protected. The kill switch and cancellation path stop execution safely.

## Phase 3B local planner governance

Qwen is permitted only through a localhost Ollama runtime. The model receives
synthetic request context and a strict CohortPlan JSON schema; it cannot select
arbitrary tools or produce SQL, code, paths, URLs, mutations, approval
decisions, or hidden reasoning. Structured output is validated and falls back
to the deterministic bounded planner on local failure. Planner lineage records
model digest, prompt hash/version, schema version, compatibility mode, timing,
token counts when supplied, validation status, and fallback reason.
## Local planner model selection

Local planner candidates are server-side allowlisted and must already be
installed in localhost-only Ollama. No API request may select an arbitrary tag
or alter the Ollama URL. Comparative evaluation runs sequentially and uses
the exact same prompt, schema, safety validators, repair limit, and
deterministic fallback. Safety is a hard gate; human approval remains
mandatory for every cohort finalization.

## MCP governance

The MCP gateway is a separate localhost-only process using the official
Python SDK. It exposes only the existing read-only registry tools. A
server-configured development client maps a credential to actor identity,
role, client type, and permitted dataset IDs; tool arguments cannot claim a
role or bypass dataset authorization. MCP request audit records redact
credentials, headers, prompts, full clinical documents, raw FHIR, and cache
paths. The global MCP kill switch prevents execution while FastAPI health and
inspection APIs remain available. This identity model is development-only and
must be replaced with production OAuth/enterprise identity before deployment.
