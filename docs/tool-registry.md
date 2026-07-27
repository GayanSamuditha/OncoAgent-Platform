# Governed tool registry

The Phase 3A registry is the single source of truth for the ten read-only
clinical tools exposed to LangGraph and the Phase 4A MCP gateway. MCP does not
duplicate SQL, retrieval, or structured-FHIR verification logic. It validates
the MCP envelope, authenticates the configured development client, checks the
dataset allowlist, then delegates to the registry.

Tools use stable `phase3a-tool-v1` descriptors, strict request validation,
role allowlists, bounded result sizes, read-only classification, and safe
error mapping. Search accepts only `medcpt`, `bioclinicalbert`, or
`postgres_fts`; MCP records the actual provider and fallback history.

MCP exposes no SQL, shell, filesystem, export, approval, model-selection, or
audit-mutation tool. Development tokens are configured only through ignored
`.env` values and are never returned by inspection APIs.
