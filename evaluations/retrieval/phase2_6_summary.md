# Phase 2.6 retrieval evaluation

This is a synthetic development evaluation on dataset `6b15ce38-e12c-4482-866e-59d333952024` (100 patients, 48 structured-ground-truth cases). It is not clinically validated and is not production performance. Scores are ranking signals, not clinical probabilities.

| Profile | P@5 | R@5 | MRR | nDCG@5 | Zero | Median ms | P95 ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| postgres_fts | 0.050 | 0.250 | 0.166 | 0.187 | 0.021 | 53.88 | 56.76 |
| bioclinicalbert | 0.017 | 0.083 | 0.038 | 0.050 | 0.000 | 16.08 | 30.77 |
| medcpt | 0.058 | 0.292 | 0.169 | 0.199 | 0.000 | 15.62 | 28.34 |
| hybrid_bioclinicalbert | 0.046 | 0.229 | 0.114 | 0.142 | 0.000 | 57.93 | 61.43 |
| hybrid_medcpt | 0.046 | 0.229 | 0.184 | 0.196 | 0.000 | 54.72 | 57.87 |
| bioclinicalbert + cross-encoder | 0.025 | 0.125 | 0.059 | 0.075 | 0.000 | 118.52 | 159.96 |
| medcpt + cross-encoder | 0.054 | 0.271 | 0.182 | 0.205 | 0.000 | 132.67 | 202.89 |
| hybrid_bioclinicalbert + cross-encoder | 0.033 | 0.167 | 0.095 | 0.114 | 0.000 | 247.69 | 289.57 |
| hybrid_medcpt + cross-encoder | 0.050 | 0.250 | 0.133 | 0.162 | 0.000 | 242.57 | 274.98 |

RRF constant was 60 and the reranker candidate pool was 20. Reranking improved, was unchanged, or worsened MRR respectively in 12.5%, 83.3%, and 4.2% of BioClinicalBERT cases; for MedCPT the figures were 12.5%, 77.1%, and 10.4%. Hybrid reranking did not justify its latency cost in this bounded sample.

## Policy decision

Recommend `medcpt` as the bounded-evaluation dense profile and `bioclinicalbert` as the dense fallback; keep `postgres_fts` available as the lower-dependency lexical fallback. Do not enable reranking by default. MedCPT had higher P@5, R@5, and nDCG than BioClinicalBERT in this expanded set, but the earlier 25-patient smoke set favored BioClinicalBERT, so this is a development recommendation requiring further evaluation rather than a production selection. This conclusion is limited by one Synthea archive, 48 cases, deterministic document templates, and PubMed-oriented model training; it is not a clinical or production claim.

## Ten failure-analysis cases

The complete machine-readable analysis is in the ignored Phase 2.6 output. The ten reviewed cases are `condition-001` through `condition-008` and `observation-001` through `observation-002`. Exact-term condition and observation queries often returned a different encounter first because the clinical document is encounter-level and common observations dominate long documents. In the reranked view, `condition-002` through `condition-008` and both observations changed away from the first-stage top result, illustrating reranker regressions and candidate-context ambiguity. These cases retain their structured labels; future work should add section-aware/chunk-level evidence and structured post-retrieval verification.
