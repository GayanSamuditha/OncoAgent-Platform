# Initial Threat Model

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

The Phase 0 API has no clinical-data endpoints and no export capability.
