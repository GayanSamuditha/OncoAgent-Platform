# Roadmap

1. **Phase 0 — Foundation:** service shell, PostgreSQL/pgvector, migrations, health APIs, frontend Overview, safety documentation, and developer checks.
2. **Phase 1 — Bounded Synthea ingestion:** stream a deterministic small sample from an archive, store selected synthetic FHIR records, normalize supported resources, preserve provenance, and expose patient/timeline APIs.
3. **Phase 2 — BioClinicalBERT retrieval:** deterministic encounter documents, tokenizer-aware chunks, lazy encoder loading, pgvector persistence, provenance-linked search, and synthetic development evaluation with CPU/MPS fallback.
4. **Phase 2.5 — Model-agnostic retrieval:** MedCPT query/article dual encoder, provider-specific lineage, BioClinicalBERT comparison, and PostgreSQL full-text baseline.
5. **Phase 2.6 — Hybrid and reranked retrieval:** Reciprocal Rank Fusion, bounded MedCPT cross-encoder reranking, comparative evaluation, failure analysis, policy selection, and the Evaluations dashboard.
6. **Phase 3A — Governed LangGraph workflow:** deterministic allowlisted planning, PostgreSQL checkpoints, retrieval fallback, structured FHIR verification, evidence provenance, approval interruption, cancellation, kill switch, and audit lineage.
7. **Phase 3B — Local Qwen planner and operations console:** local-only structured planning, deterministic fallback, prompt/model lineage, workflow console, approval queue, audit explorer, and agent catalog.
8. **Phase 4A — Governed MCP tool gateway:** official Python MCP SDK, read-only registry tools, development identity, dataset isolation, Streamable HTTP/stdio, and MCP audit lineage.
9. **Phase 4B — Full-stack workflow experience:** researcher run console, evidence views, approval review, lineage, and audit exploration.
10. **Phase 5 — MCP and CrewAI interoperability:** expose platform tools and demonstrate CrewAI as a downstream consumer; neither becomes the core runtime.
10. **Phase 6 — Temporal and Ray:** add durable orchestration and batch embedding/evaluation only after the vertical MVP is stable.
11. **Phase 7 — Kubernetes and controlled releases:** package deployment, monitoring, shadow/canary workflows, and operational runbooks.

No phase may introduce real patient data or clinical-validation claims.
