# Governance Controls

## Data

Only synthetic Synthea data is permitted. Archives, extracted FHIR files, generated patient records, embeddings, and database volumes are local or external artifacts and must remain outside Git. Phase 1 stores raw FHIR JSON only for a bounded selected sample, with archive/member provenance. The platform must remain clearly labeled as not clinically validated.

## Traceability

Dataset and ingestion runs record archive identity, sample policy, requested limit, counts, status, and failure information. Raw resources retain source archive name, member path, and member hash. Future workflow runs must additionally record agent/node, prompt version, model version, tool schema/version, evidence references, and human decisions.

## Secrets and access

Credentials are supplied through environment variables. `.env` files, tokens, and production credentials are forbidden in source control. Future roles will separate researchers, reviewers, and administrators, with least-privilege database access.

## Dependency and model risk

Dependencies require a present implementation need. Deferred agent, orchestration, and deployment frameworks must not be installed early. Future model evaluations must use documented synthetic fixtures and must not be presented as clinical performance.
