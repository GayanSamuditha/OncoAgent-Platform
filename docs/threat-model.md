# Initial Threat Model

## Phase 7C security-readiness scope

Actors include unauthenticated users, researchers, reviewers, governance
officers, auditors, operators, administrators, compromised browser sessions
and service identities, malicious MCP clients, prompt-injection content,
compromised local-model responses, database insiders, compromised containers,
and dependency supply-chain attackers.

Assets include identity and service credentials, dataset grants, synthetic
FHIR data, workflow and Temporal state, approval and audit records, provenance
evidence, prompts and outputs, release evidence, backups, MCP lineage, and
telemetry. Boundaries are browser/API, API/PostgreSQL, API/Temporal,
worker/MCP, MCP/PostgreSQL, services/Ollama, services/telemetry,
container/host, and backup/restore.

Application RBAC and dataset grants do not replace MCP authorization.
Retrieved content is untrusted data; structured verification, tool schemas,
allowlists, provenance, and human review remain authoritative. Implemented
controls include centralized permissions, reviewer separation of duties,
CSRF Origin validation, bounded concurrency/request limits, redacted
telemetry, non-root images, isolated Temporal persistence, and audit-chain
verification for new access decisions. Scanner availability and historical
audit records are reported as `not_evaluable` or `legacy_unverified`, never
silently passed. Local identity, HTTP, host Ollama, synthetic data, and the
absence of an external immutable ledger are development limitations.

| Threat | Control in Phase 0 | Future control |
| --- | --- | --- |
| Raw Synthea data accidentally committed | Explicit Git ignores and project rules | CI artifact scanning |
| Secret or token leakage | `.env` and credential patterns ignored | Secret scanning and managed secrets |
| Database unavailable | `/ready` dependency check and Compose healthcheck | Dependency monitoring |
| Untraceable agent behavior | Structured JSON logs and versioned API foundation | Run/step/tool/model lineage |
| Semantic retrieval treated as fact | Not implemented in Phase 0 | Structured FHIR verification gate |
| Unsupported clinical use | UI and documentation safety notices | Product access controls and review policy |
| Dependency supply-chain risk | Minimal pinned major-version ranges and explicit review rule | Lockfiles, scanning, provenance |
| Model risk or invented metrics | No model runtime or metrics in Phase 0 | Synthetic evaluation protocol and review |
| Hybrid/reranker overconfidence | Scores exposed as ranking signals with separate lineage | Structured FHIR verification before any future cohort decision |
| Candidate-pool resource exhaustion | Maximum 50 candidates and bounded reranker batches | Operational quotas and workload isolation |
| Cross-dataset leakage | Dataset filters applied to lexical and vector branches | Authorization-scoped dataset access |
| Unapproved cohort finalization | LangGraph interrupt, reviewer/admin decision, terminal-state protection | External approval service and segregation-of-duties controls |
| Tool misuse or arbitrary execution | Pydantic allowlisted registry, read-only tools, bounded arguments and retries | Signed tool manifests and authorization service |
| Checkpoint/audit divergence | Separate PostgreSQL checkpoint and application audit writes with run/thread correlation | Reconciliation jobs and immutable audit storage |
| Development identity misuse | Explicit actor headers documented as simulation only | Production authentication, authorization, and identity federation |
| Hosted model or patient-data egress | Localhost-only Ollama URL validation; no hosted provider dependency | Network policy and production identity controls |
| Prompt injection or unsafe planner output | Schema validation, allowlisted criteria/tools, deterministic fallback, no reasoning persistence | Signed prompt registry and adversarial CI suite |
| MCP credential misuse | Localhost-only transport, server-side client allowlist, token redaction, role and dataset checks | Production OAuth and identity federation |
| MCP arbitrary tool execution | Exact registry catalog, strict Pydantic envelopes, read-only descriptors, no SQL/shell/filesystem tools | Signed tool manifests and centralized authorization |
| MCP response exfiltration | Synthetic-only dataset policy, result/byte limits, approved structured fields, no raw FHIR | DLP and network policy |
| Downstream CrewAI bypasses platform controls | MCP-only adapters, per-agent allowlists, client/dataset authorization, no direct DB/FHIR handles | Production identity and network enforcement |
| CrewAI self-approval or unsupported brief | Structured outputs, provenance checks, mandatory separate human review, terminal decisions | External review service |
| Identity spoofing or stale privilege | Signed local session claims, issuer/audience/expiry validation, server-side RBAC, dataset grants, disabled-user checks, append-only access decisions | Production OIDC federation and enterprise identity lifecycle |
| Reviewer privilege abuse | Persisted reviewer assignment, dataset grant, separation of duties, terminal decision uniqueness | Hospital IAM and privileged access management |

The Phase 0 API has no clinical-data endpoints and no export capability.
