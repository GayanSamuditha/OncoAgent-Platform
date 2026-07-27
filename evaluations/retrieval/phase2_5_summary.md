# Phase 2.5 Retrieval Evaluation

This document is a template for the bounded synthetic development evaluation. Run `scripts/evaluate_clinical_retrieval.py` after PostgreSQL and all three retrieval profiles are available, then record the measured output here. Results are not clinically validated and are not evidence of production performance.

Profiles: PostgreSQL full-text, BioClinicalBERT comparison encoder, and MedCPT dual encoder. The same deterministic encounter documents, dataset filter, document type, and top-k settings must be used for each profile.

Measured run on `synthea-dev-25` (18 cases; encounter documents; patient-level de-duplication):

| Profile | P@5 | R@5 | MRR | nDCG@5 | Zero-result | Median ms | P95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| PostgreSQL FTS | 0.050 | 0.250 | 0.208 | 0.219 | 0.375 | 5.71 | 11.93 |
| BioClinicalBERT | 0.088 | 0.438 | 0.346 | 0.368 | 0.000 | 20.33 | 35.05 |
| MedCPT | 0.088 | 0.438 | 0.318 | 0.348 | 0.000 | 18.59 | 25.84 |

Category-level P@5 / R@5:

- PostgreSQL FTS: condition 0.000/0.000; observation 0.000/0.000; procedure 0.200/1.000; medication 0.000/0.000; diagnostic-report 0.100/0.500; combined 0.000/0.000.
- BioClinicalBERT: condition 0.067/0.333; observation 0.067/0.333; procedure 0.200/1.000; medication 0.067/0.333; diagnostic-report 0.100/0.500; combined 0.000/0.000.
- MedCPT: condition 0.000/0.000; observation 0.067/0.333; procedure 0.200/1.000; medication 0.067/0.333; diagnostic-report 0.100/0.500; combined 0.100/0.500.

These are synthetic development results only, not clinically validated and not evidence of production performance. MedCPT was not superior to BioClinicalBERT on this bounded sample; the measured result does not support that claim.
