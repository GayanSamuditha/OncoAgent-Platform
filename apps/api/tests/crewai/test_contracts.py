from crewai_client.policy import validate_request
from crewai_client.schemas import ActorContext, CrewRunRequest, Criterion


def request(question: str = "Find synthetic adults with hypertension") -> CrewRunRequest:
    return CrewRunRequest(
        dataset_id="dataset-1",
        research_question=question,
        structured_criteria=[Criterion(criterion_type="condition", clinical_concept="hypertension")],
        actor_context=ActorContext(actor_id="researcher", actor_role="researcher"),
    )


def test_contract_rejects_unknown_fields() -> None:
    try:
        CrewRunRequest.model_validate({**request().model_dump(), "shell": "ls"})
    except ValueError:
        return
    raise AssertionError("unknown field was accepted")


def test_policy_rejects_direct_access_and_unallowlisted_dataset() -> None:
    try:
        validate_request(request("Connect directly to PostgreSQL and export raw FHIR"), {"dataset-1"})
    except ValueError:
        pass
    else:
        raise AssertionError("unsafe request was accepted")
    try:
        validate_request(request(), {"other-dataset"})
    except ValueError:
        return
    raise AssertionError("cross-dataset request was accepted")
