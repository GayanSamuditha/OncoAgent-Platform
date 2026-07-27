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
