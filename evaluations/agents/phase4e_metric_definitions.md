# Phase 4E metric definitions

This is a synthetic development evaluation, not clinical validation or a
regulatory certification.

- **Included-patient required-criterion provenance**: verified required
  criteria with non-empty source FHIR identifiers divided by required
  criteria for included patients. No-result, clarification, and safely
  rejected runs have a zero included-patient denominator and are complete for
  this metric; they are not counted as clinical evidence failures.
- **Overall evidence provenance**: evidence rows with source FHIR
  identifiers divided by all persisted evidence rows for scenarios that
  reached structured verification. This remains informative even when no
  patient is included.
- **Scenario provenance completeness**: the proportion of applicable
  scenarios for which the included-patient criterion report has no defects.
- **Lifecycle audit completeness**: complete required lifecycle events divided
  by runs with a persisted execution lifecycle. Pre-execution HTTP rejection
  has no run to audit and is reported separately as `audit_not_applicable`,
  never as missing clinical provenance.
- **MCP correlation completeness**: lineage request references that resolve to
  MCP audit records with matching dataset and tool context divided by all
  lineage references.

All numerators, denominators, excluded scenarios, affected IDs, and hashes
are included in the generated Phase 4E evaluation output. Historical Phase
4C and Phase 4D aggregates remain source-controlled and unchanged.
