"""CrewAI remains a protocol consumer and cannot access clinical storage."""

import ast
from pathlib import Path


def test_crewai_client_has_no_direct_clinical_storage_imports() -> None:
    root = Path(__file__).parents[3].parent / "crewai_client"
    prohibited = ("sqlalchemy", "psycopg", "app.db", "app.repositories", "app.ingestion", "app.fhir")
    for path in root.glob("*.py"):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [item.name for item in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            assert not any(name.startswith(prefix) for name in names for prefix in prohibited), path
