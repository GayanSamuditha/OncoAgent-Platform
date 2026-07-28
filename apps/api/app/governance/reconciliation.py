"""Read-only reconciliation of CrewAI lineage and MCP audit references."""

from collections.abc import Iterable, Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ReconciliationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    referenced_request_count: int = Field(ge=0)
    observed_request_count: int = Field(ge=0)
    orphan_mcp_request_ids: list[str] = []
    duplicate_mcp_request_ids: list[str] = []
    dataset_mismatches: list[str] = []
    correlation_mismatches: list[str] = []
    complete: bool


def reconcile_mcp_lineage(
    lineage_request_ids: Iterable[str],
    observed_requests: Iterable[Mapping[str, Any]],
    dataset_id: str | None = None,
) -> ReconciliationReport:
    refs = [str(item) for item in lineage_request_ids]
    observed = list(observed_requests)
    by_id = {str(item.get("id")): item for item in observed}
    orphan = sorted(set(refs) - set(by_id))
    duplicates = sorted({item for item in refs if refs.count(item) > 1})
    mismatches: list[str] = []
    datasets: list[str] = []
    for request_id in set(refs) & set(by_id):
        row = by_id[request_id]
        if dataset_id and row.get("dataset_id") != dataset_id:
            datasets.append(request_id)
        if row.get("correlation_id") and row.get("id") != request_id:
            mismatches.append(request_id)
    return ReconciliationReport(
        referenced_request_count=len(refs),
        observed_request_count=len(observed),
        orphan_mcp_request_ids=orphan,
        duplicate_mcp_request_ids=duplicates,
        dataset_mismatches=sorted(set(datasets)),
        correlation_mismatches=sorted(set(mismatches)),
        complete=not orphan and not duplicates and not datasets and not mismatches,
    )
