# Retrieval policy

The governed workflow uses MedCPT as the primary dense candidate retriever,
BioClinicalBERT as fallback, and PostgreSQL full-text search as final fallback.
Reranking is disabled by default. Every attempt and fallback reason is audited.
Retrieval is candidate generation only; normalized structured FHIR verification
is authoritative and precedes approval.
