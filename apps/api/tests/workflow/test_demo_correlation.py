from app.workflow.schemas import RunCreateRequest


def test_run_request_accepts_bounded_demo_correlation() -> None:
    request = RunCreateRequest(
        dataset_id="dataset-a",
        request="Find synthetic patients with diabetes.",
        correlation_id="client-demo-20260729-150500-langgraph",
    )

    assert request.correlation_id == "client-demo-20260729-150500-langgraph"
