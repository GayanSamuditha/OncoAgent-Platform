# Cross-framework selection policy

This policy is based on equivalent synthetic development scenarios and is
not clinically validated or production performance. LangGraph and CrewAI are
not interchangeable runtimes, so the policy intentionally does not declare a
universal winner.

## LangGraph

Use LangGraph for regulated operational workflows that require explicit state
transitions, PostgreSQL-backed checkpoints, approval interrupts, structured
FHIR verification, and restart/resume behavior. It remains the platform
control plane.

## CrewAI

Use CrewAI for bounded downstream specialist collaboration, MCP-only evidence
gathering, and research-brief drafting. Delegation and memory remain disabled;
every result requires separate human review. Local CrewAI execution is not
durable across process failure and must not replace LangGraph.

## Required interpretation

Compare completion, evidence, safety, auditability, latency, and recovery as
separate dimensions. Do not trade away approval, provenance, dataset
isolation, or MCP controls to improve a framework score.
