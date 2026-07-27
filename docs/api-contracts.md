# Phase 0 API Contracts

## `GET /health`

Returns HTTP 200 when the API process is running. It does not query PostgreSQL.

```json
{"status":"ok","service":"OncoAgent Platform API","version":"0.1.0"}
```

## `GET /ready`

Queries PostgreSQL with `SELECT 1`. It returns HTTP 200 with `status: ready` when available and HTTP 503 with `status: not_ready` when unavailable.

## `GET /api/v1/platform/info`

Returns platform identity, the synthetic-only policy, the not-clinically-validated status, and separate implemented/planned capability lists.
