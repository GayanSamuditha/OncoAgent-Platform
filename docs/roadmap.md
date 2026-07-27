# Roadmap

1. **Phase 0 — Foundation:** service shell, PostgreSQL/pgvector, migrations, health APIs, frontend Overview, safety documentation, and developer checks.
2. **Phase 1 — Bounded Synthea ingestion:** stream a deterministic small sample from an archive, store selected synthetic FHIR records, normalize supported resources, preserve provenance, and expose patient/timeline APIs.
3. **Phase 2 — BioClinicalBERT retrieval:** deterministic encounter documents, tokenizer-aware chunks, lazy encoder loading, pgvector persistence, provenance-linked search, and synthetic development evaluation with CPU/MPS fallback.
4. **Phase 3 — LangGraph governed workflow:** structured planning, specialized workers, FHIR verification, trace persistence, and approval interruption.
5. **Phase 4 — Full-stack workflow experience:** researcher run console, evidence views, approval review, lineage, and audit exploration.
6. **Phase 5 — MCP and CrewAI interoperability:** expose platform tools and demonstrate CrewAI as a downstream consumer; neither becomes the core runtime.
7. **Phase 6 — Temporal and Ray:** add durable orchestration and batch embedding/evaluation only after the vertical MVP is stable.
8. **Phase 7 — Kubernetes and controlled releases:** package deployment, monitoring, shadow/canary workflows, and operational runbooks.

No phase may introduce real patient data or clinical-validation claims.
