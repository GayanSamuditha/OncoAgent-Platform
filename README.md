# OncoAgent Platform

OncoAgent Platform is an enterprise-style foundation for governed agentic AI workflows over synthetic Synthea healthcare data. It is designed as a portfolio project for regulated healthcare machine-learning engineering. The project is not clinically validated and must not be used for clinical decisions.

## Current status

Phase 1 through Phase 2.6 are implemented in bounded local form: deterministic clinical documents, tokenizer-aware chunks, model-agnostic retrieval providers, MedCPT dual-encoder support, BioClinicalBERT comparison support, PostgreSQL full-text baseline, exact pgvector search, hybrid Reciprocal Rank Fusion, optional bounded MedCPT cross-encoder reranking, provenance APIs, and a retrieval evaluation dashboard. These models are encoders/rankers, not generative models or clinical decision-makers, and are not clinically validated. LangGraph workflows, cohort search, and approval workflows are not implemented.

Phase 2 smoke test:

```bash
apps/api/.venv/bin/python scripts/build_clinical_documents.py --dataset-id <dataset-id> --document-type encounter --limit 25
apps/api/.venv/bin/python scripts/index_clinical_documents.py --dataset-id <dataset-id> --model emilyalsentzer/Bio_ClinicalBERT --batch-size 4 --limit 25
apps/api/.venv/bin/python scripts/index_clinical_documents.py --dataset-id <dataset-id> --retrieval-provider medcpt --batch-size 4 --limit 25
curl -X POST http://localhost:8000/api/v1/clinical-search -H 'content-type: application/json' -d '{"dataset_id":"<dataset-id>","query":"hypertension elevated blood pressure","top_k":5,"document_types":["encounter"]}'
```

MedCPT uses `ncbi/MedCPT-Query-Encoder` for queries and `ncbi/MedCPT-Article-Encoder` for documents, CLS pooling, 64-token query input, and 512-token document input. BioClinicalBERT remains available as a separate mean-pooling comparison profile. PostgreSQL full-text search is the non-neural baseline. Search scores are ranking signals, not clinical probabilities. MedCPT’s PubMed-oriented training domain is a limitation for synthetic FHIR phrasing. Model weights, Hugging Face caches, generated embeddings, and evaluation outputs remain local-only and ignored by Git.

Phase 2.6 adds `hybrid_bioclinicalbert` and `hybrid_medcpt`, using deterministic Reciprocal Rank Fusion with a documented constant of 60. `ncbi/MedCPT-Cross-Encoder` is an optional, bounded reranker over at most 50 candidates; its logits are ranking signals and are never treated as calibrated probabilities. The source-controlled 100-patient evaluation definition is generated from normalized Synthea facts. Run the comparative evaluation with:

```bash
DATABASE_URL=postgresql+psycopg://oncoagent:oncoagent_dev@localhost:55432/oncoagent \
apps/api/.venv/bin/python scripts/evaluate_clinical_retrieval.py \
  --dataset-id <100-patient-dataset-id> \
  --evaluation-file evaluations/retrieval/phase2_6_cases.json
```

Machine-readable results are written to ignored `evaluation_outputs/`; the `/evaluations` page displays only measured results. The current bounded policy recommends MedCPT as the dense default, BioClinicalBERT as dense fallback, and no reranker by default. Hybrid and reranked profiles did not justify their added latency. The earlier 25-patient smoke set favored BioClinicalBERT, so this remains a development recommendation rather than a production selection. All findings are synthetic development evaluation only, not production performance.

Only synthetic Synthea data is supported. Raw archives are local inputs and are ignored by Git.

## Architecture

The current slice is `Next.js → FastAPI → PostgreSQL`. The future target adds bounded Synthea ingestion, BioClinicalBERT retrieval, LangGraph planning/execution, structured FHIR verification, human approval, and audit lineage. See [docs/architecture.md](docs/architecture.md) and [docs/roadmap.md](docs/roadmap.md).

## Prerequisites

- Python 3.12
- Node.js 20 or newer and npm
- Docker Desktop with Compose

## Setup

From the repository root:

```bash
cp .env.example .env
make install
```

The local virtual environment is created at `apps/api/.venv`; generated dependencies are ignored.

## Start the database

```bash
make db-up
make migrate
```

PostgreSQL is available at `localhost:${POSTGRES_HOST_PORT:-55432}`. Set `POSTGRES_HOST_PORT` in `.env` if another local port is required. The Compose volume is local development state and is not committed.

## Inspect and import a bounded Synthea sample

Inspection streams archive metadata and does not extract files:

```bash
python3.12 scripts/inspect_synthea_archive.py \
  --archive synthea_1m_fhir_1_8/output_11_20170227T084456.tar.gz
```

Import starts with a small deterministic sample. The default is 100 patients and the recommended first validation run is 25. The local safety maximum is 1,000 unless `--unsafe-override` is explicitly provided.

```bash
DATABASE_URL=postgresql+psycopg://oncoagent:oncoagent_dev@localhost:55432/oncoagent \
apps/api/.venv/bin/python scripts/import_synthea_sample.py \
  --archive synthea_1m_fhir_1_8/output_11_20170227T084456.tar.gz \
  --patient-limit 25 \
  --dataset-name synthea-dev-25
```

The importer stores normalized supported resources and raw JSON with archive/member provenance. Re-running the same dataset is idempotent through dataset/resource uniqueness constraints. It stores only the selected patient-containing bundles; it does not create a FHIR server or process the complete one-million-patient corpus.

## Start the applications

In separate terminals:

```bash
make backend-dev
make frontend-dev
```

Open <http://localhost:3000>. The API is available at <http://localhost:8000> and its OpenAPI document is at <http://localhost:8000/docs>.

## Verification commands

```bash
make test
make lint
make typecheck
make check
```

Individual API checks:

```bash
curl http://localhost:8000/health
curl -i http://localhost:8000/ready
curl http://localhost:8000/api/v1/platform/info
```

## Shutdown and cleanup

```bash
make db-down
```

`make db-down` stops the container and preserves the local PostgreSQL volume. To remove only the Phase 0 development database volume after confirming it is disposable:

```bash
docker compose -f infra/docker-compose.yml down -v
```

Never remove or alter the Synthea archive directory as part of local cleanup.

## Troubleshooting

- If `/health` fails, start the backend with `make backend-dev` and inspect the terminal logs.
- If `/ready` returns `503`, run `docker compose -f infra/docker-compose.yml ps` and `docker compose -f infra/docker-compose.yml logs postgres`.
- If migration cannot connect, confirm that `DATABASE_URL` in `.env` matches the Compose credentials and that `make db-up` completed.
- If the frontend shows the backend as unavailable, confirm that the API is listening on port 8000 and that `NEXT_PUBLIC_API_BASE_URL` is correct.
- If Docker cannot pull the pgvector image, check Docker Desktop connectivity; no application data is extracted or modified by the platform foundation.
- If host port 5432 is occupied, set `POSTGRES_HOST_PORT=55432` and use the matching `DATABASE_URL` port.

## Safety and governance

See [docs/governance.md](docs/governance.md) and [docs/threat-model.md](docs/threat-model.md). Do not commit archives, extracted FHIR data, model weights, embeddings, database volumes, secrets, tokens, or `.env` files. Do not invent metrics or describe the platform as clinically validated.
