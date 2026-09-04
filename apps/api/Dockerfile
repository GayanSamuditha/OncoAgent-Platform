# syntax=docker/dockerfile:1.7

FROM python:3.12.11-slim-bookworm AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_EXTRA_INDEX_URL=https://download.pytorch.org/whl/cpu
WORKDIR /build

RUN python -m pip install --upgrade pip==25.1.1
COPY apps/api/pyproject.toml /build/apps/api/
COPY apps/crewai_client/pyproject.toml /build/apps/crewai_client/
COPY apps/api/app /build/apps/api/app
COPY apps/crewai_client /build/apps/crewai_client
COPY apps/mcp_server /build/apps/mcp_server

RUN python -m pip wheel --no-cache-dir --wheel-dir /wheels \
    /build/apps/api /build/apps/crewai_client

FROM python:3.12.11-slim-bookworm AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/opt/oncoagent \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /opt/oncoagent

RUN groupadd --system --gid 10001 oncoagent \
    && useradd --system --uid 10001 --gid 10001 --create-home --home-dir /home/oncoagent oncoagent \
    && python -m pip install --no-cache-dir --upgrade pip==25.1.1
COPY --from=builder /wheels /wheels
RUN python -m pip install --no-cache-dir /wheels/*.whl \
    && rm -rf /wheels
COPY --chown=oncoagent:oncoagent apps/mcp_server /opt/oncoagent/apps/mcp_server
COPY --chown=oncoagent:oncoagent apps/api/alembic /opt/oncoagent/apps/api/alembic
COPY --chown=oncoagent:oncoagent apps/api/alembic.ini /opt/oncoagent/apps/api/alembic.ini
COPY --chown=oncoagent:oncoagent scripts /opt/oncoagent/scripts

USER oncoagent

FROM runtime AS api-runtime
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM runtime AS mcp-runtime
CMD ["python", "-m", "apps.mcp_server.server", "--transport", "streamable-http"]

FROM runtime AS worker-runtime
CMD ["python", "scripts/run_temporal_worker.py"]

FROM runtime AS evaluation-runtime
CMD ["python", "-m", "http.server", "8088"]
