import os

import pytest
from langgraph.checkpoint.postgres import PostgresSaver

from app.workflow.graph import build_graph


@pytest.mark.skipif(not os.getenv("RUN_WORKFLOW_DB_TESTS"), reason="set RUN_WORKFLOW_DB_TESTS=1 for PostgreSQL checkpointer integration")
def test_postgres_checkpointer_compiles_graph() -> None:
    database_url = os.environ["ONCOAGENT_TEST_DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")
    with PostgresSaver.from_conn_string(database_url) as saver:
        saver.setup()
        graph = build_graph(saver)
        assert graph is not None
