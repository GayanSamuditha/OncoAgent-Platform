"""The Phase 3A persistent, approval-gated LangGraph workflow."""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.ingestion import Dataset
from app.models.workflow import ApprovalDecision, ApprovalRequest
from app.retrieval.model_registry import provider_for
from app.retrieval.search import postgres_fts_search, search
from app.workflow.audit import (
    create_approval,
    event,
    existing_decision,
    lineage,
    policy,
    save_candidates,
    save_evidence,
    step,
    tool_call,
    update_run,
)
from app.workflow.planner import DeterministicCohortPlanner, plan_to_dict
from app.workflow.schemas import CohortPlan, Criterion, WorkflowState
from app.workflow.tools import (
    ToolExecutionContext,
    ToolExecutionError,
    build_tool_registry,
    execute_tool,
)


def _utc() -> str:
    return datetime.now(UTC).isoformat()


def _fail(state: WorkflowState, message: str, status: str = "failed") -> dict[str, Any]:
    errors = list(state.get("errors", []))
    errors.append(message)
    return {"errors": errors, "run_status": status, "current_node": "fail_safely", "updated_at": _utc()}


def _node_started(state: WorkflowState, name: str) -> None:
    run_id = state["run_id"]
    update_run(run_id, current_node=name, status=state.get("run_status", "running"))
    step(run_id, name, "started")
    event(run_id, state["run_id"], "node_started", name)


def intake(state: WorkflowState) -> dict[str, Any]:
    _node_started(state, "intake")
    settings = get_settings()
    with SessionLocal() as session:
        dataset = session.get(Dataset, state["dataset_id"])
    if dataset is None:
        return _fail(state, "dataset not found", "failed")
    if not settings.agent_execution_enabled:
        policy(state["run_id"], "kill_switch", "deny", "Agent execution is disabled by platform policy.")
        return _fail(state, "Agent execution is disabled by the platform kill switch.", "failed")
    return {"run_status": "planning", "current_node": "intake", "updated_at": _utc()}


def create_plan(state: WorkflowState) -> dict[str, Any]:
    _node_started(state, "create_plan")
    try:
        criteria = [Criterion.model_validate(item) for item in state.get("structured_input", {}).get("criteria", [])] or None
        plan = DeterministicCohortPlanner().plan(state["original_request"], state["dataset_id"], criteria, int(state["structured_input"].get("max_candidates", 20)))
    except (ValueError, TypeError) as exc:
        return _fail(state, str(exc), "needs_clarification")
    plan_dict = plan_to_dict(plan)
    update_run(state["run_id"], structured_plan=plan_dict, retrieval_policy={"primary": "medcpt", "fallbacks": ["bioclinicalbert", "postgres_fts"], "reranker": "none"})
    lineage(state["run_id"], "planner", "deterministic-cohort-planner", "phase3a-planner-v1", {"plan_version": plan.plan_version})
    return {"structured_plan": plan_dict, "plan_version": plan.plan_version, "planner_provider": "deterministic-cohort-planner-v1", "requested_criteria": [item.model_dump(mode="json") for item in plan.criteria], "retrieval_policy": {"primary": "medcpt", "fallbacks": ["bioclinicalbert", "postgres_fts"], "reranker": "none"}, "run_status": "validating_plan", "current_node": "create_plan", "updated_at": _utc()}


def validate_plan(state: WorkflowState) -> dict[str, Any]:
    _node_started(state, "validate_plan")
    try:
        plan = CohortPlan.model_validate(state.get("structured_plan", {}))
        registry = build_tool_registry()
        unknown = set(plan.required_tools) - set(registry)
        if unknown:
            raise ValueError(f"unregistered tools in plan: {sorted(unknown)}")
        if plan.dataset_id != state["dataset_id"]:
            raise ValueError("plan dataset does not match requested dataset")
    except (ValueError, TypeError) as exc:
        return _fail(state, f"invalid plan: {exc}", "failed")
    return {"run_status": "validating_plan", "current_node": "validate_plan", "updated_at": _utc()}


def policy_precheck(state: WorkflowState) -> dict[str, Any]:
    _node_started(state, "policy_precheck")
    settings = get_settings()
    if not settings.agent_execution_enabled:
        policy(state["run_id"], "precheck", "deny", "Agent execution kill switch is disabled.")
        return _fail(state, "Agent execution is disabled by the platform kill switch.")
    if int(state["structured_plan"]["max_candidates"]) > settings.workflow_max_candidates:
        return _fail(state, "requested candidate limit exceeds workflow policy")
    policy(state["run_id"], "precheck", "allow", "Bounded read-only plan and synthetic dataset accepted.", {"max_candidates": state["structured_plan"]["max_candidates"]})
    return {"run_status": "retrieving", "current_node": "policy_precheck", "updated_at": _utc()}


def retrieve_candidates(state: WorkflowState) -> dict[str, Any]:
    _node_started(state, "retrieve_candidates")
    settings = get_settings()
    plan = state["structured_plan"]
    attempts = list(state.get("retrieval_attempts", []))
    fallbacks = list(state.get("retrieval_fallbacks", []))
    last_error = ""
    candidates: list[dict[str, Any]] = []
    for provider_name in ["medcpt", "bioclinicalbert", "postgres_fts"]:
        attempts.append({"provider": provider_name, "started_at": _utc()})
        try:
            if provider_name == "postgres_fts":
                with SessionLocal() as session:
                    results, latency = postgres_fts_search(session, state["dataset_id"], plan["retrieval_query"], int(plan["max_candidates"]), ["encounter", "patient-summary"], None)
            else:
                provider = provider_for(settings, provider_name)
                provider.load()
                with SessionLocal() as session:
                    results, latency = search(session, provider, state["dataset_id"], plan["retrieval_query"], int(plan["max_candidates"]), ["encounter", "patient-summary"], None, None)
            dedup: dict[str, dict[str, Any]] = {}
            for result in results:
                patient_id = str(result["patient_id"])
                dedup.setdefault(patient_id, {**result, "retrieval_provider": provider_name})
                dedup[patient_id].setdefault("document_ids", []).append(str(result["document_id"]))
            candidates = list(dedup.values())[: int(plan["max_candidates"])]
            attempts[-1].update({"status": "success", "latency_ms": latency, "candidate_count": len(candidates)})
            if provider_name != "medcpt":
                fallbacks.append({"from": "medcpt" if provider_name == "bioclinicalbert" else "dense", "to": provider_name, "reason": last_error or "previous provider unavailable"})
            tool_call(state["run_id"], "search_clinical_documents", "phase3a-tool-v1", "success", {"dataset_id": state["dataset_id"], "query_length": len(plan["retrieval_query"]), "top_k": plan["max_candidates"]}, {"provider": provider_name, "candidate_count": len(candidates)}, fallbacks[-1]["reason"] if fallbacks else None)
            break
        except Exception as exc:
            last_error = f"{provider_name}: {type(exc).__name__}: {exc}"
            attempts[-1].update({"status": "failed", "error": last_error})
            fallbacks.append({"from": provider_name, "to": "next", "reason": last_error})
            tool_call(state["run_id"], "search_clinical_documents", "phase3a-tool-v1", "error", {"dataset_id": state["dataset_id"], "query_length": len(plan["retrieval_query"]), "top_k": plan["max_candidates"]}, {}, last_error, type(exc).__name__)
    if not candidates and last_error and attempts and all(item.get("status") == "failed" for item in attempts):
        return _fail({**state, "retrieval_attempts": attempts, "retrieval_fallbacks": fallbacks}, f"all retrieval providers failed: {last_error}")
    save_candidates(state["run_id"], state["dataset_id"], candidates)
    return {"retrieval_attempts": attempts, "retrieval_fallbacks": fallbacks, "candidate_results": candidates, "candidate_patient_ids": [str(item["patient_id"]) for item in candidates], "candidate_document_ids": [str(item["document_id"]) for item in candidates], "run_status": "verifying", "current_node": "retrieve_candidates", "updated_at": _utc()}


def _concept_match(item: dict[str, Any], criterion: dict[str, Any]) -> bool:
    haystack = " ".join(str(item.get(key) or "") for key in ("display", "code", "value_text", "category", "encounter_type_display", "encounter_class")).lower()
    concept = str(criterion.get("clinical_concept") or criterion.get("value") or "").lower()
    code = str(criterion.get("code") or "").lower()
    synonym_match = concept == "elevated blood pressure" and "blood pressure" in haystack
    return bool((concept and concept in haystack) or synonym_match or (code and code == str(item.get("code") or "").lower()))


def _age(birth_date: str | None) -> int | None:
    if not birth_date:
        return None
    born = datetime.fromisoformat(birth_date[:10]).date()
    today = datetime.now(UTC).date()
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


def structured_fhir_verification(state: WorkflowState) -> dict[str, Any]:
    _node_started(state, "structured_fhir_verification")
    registry = build_tool_registry()
    plan = state["structured_plan"]
    evidence: list[dict[str, Any]] = []
    verification: list[dict[str, Any]] = []
    with SessionLocal() as session:
        context = ToolExecutionContext(session, get_settings(), state["actor_context"]["role"])
        for patient_id in state.get("candidate_patient_ids", []):
            patient_results: list[dict[str, Any]] = []
            for criterion in plan["criteria"]:
                criterion_id = criterion["criterion_id"]
                try:
                    tool_name = criterion["verification_tool"]
                    result = execute_tool(registry, tool_name, context, {"dataset_id": state["dataset_id"], "patient_id": patient_id}) if tool_name != "verify_date_window" else {"items": []}
                    items = result.get("items", [result])
                    if criterion["criterion_type"] in {"minimum_age", "maximum_age", "gender"}:
                        demographic = execute_tool(registry, "get_patient_demographics", context, {"dataset_id": state["dataset_id"], "patient_id": patient_id})
                        age = _age(demographic.get("birth_date"))
                        if criterion["criterion_type"] == "gender":
                            matched = str(demographic.get("gender") or "").lower() == str(criterion.get("value") or "").lower()
                            value = {"gender": demographic.get("gender"), "source_resource_id": demographic.get("source_resource_id")}
                        else:
                            threshold = int(criterion.get("value") or 0)
                            matched = age is not None and (age >= threshold if criterion["criterion_type"] == "minimum_age" else age <= threshold)
                            value = {"age": age, "source_resource_id": demographic.get("source_resource_id")}
                    else:
                        matched_item = next((item for item in items if _concept_match(item, criterion)), None)
                        matched = matched_item is not None
                        value = matched_item or {}
                    status = "verified" if matched else ("missing_data" if not items else "not_verified")
                    tool_call(state["run_id"], tool_name, "phase3a-tool-v1", "success", {"dataset_id": state["dataset_id"], "patient_id": patient_id, "criterion_id": criterion_id}, {"verification_status": status, "source_present": bool(value.get("source_resource_id")) if isinstance(value, dict) else False})
                    patient_results.append({"criterion_id": criterion_id, "status": status})
                    evidence.append({"patient_id": patient_id, "criterion_id": criterion_id, "criterion_description": str(criterion.get("clinical_concept") or criterion.get("criterion_type")), "verification_status": status, "structured_value": value, "source_resource_type": criterion["criterion_type"], "source_fhir_resource_id": (value.get("source_resource_id") if isinstance(value, dict) else None), "encounter_id": value.get("encounter_id") if isinstance(value, dict) else None, "effective_timestamp": None, "explanation": "Verified against normalized structured synthetic FHIR facts." if matched else "Required structured fact was not verified.", "verification_tool": tool_name, "verification_tool_version": "phase3a-tool-v1", "dataset_id": state["dataset_id"]})
                except (ToolExecutionError, ValueError, KeyError) as exc:
                    patient_results.append({"criterion_id": criterion_id, "status": "missing_data"})
                    evidence.append({"patient_id": patient_id, "criterion_id": criterion_id, "criterion_description": str(criterion.get("clinical_concept") or criterion.get("criterion_type")), "verification_status": "missing_data", "structured_value": {}, "source_resource_type": None, "source_fhir_resource_id": None, "encounter_id": None, "effective_timestamp": None, "explanation": f"Verification failed safely: {exc}", "verification_tool": criterion.get("verification_tool", "unknown"), "verification_tool_version": "phase3a-tool-v1", "dataset_id": state["dataset_id"]})
            verification.append({"patient_id": patient_id, "criteria": patient_results})
    save_evidence(state["run_id"], evidence)
    included = [item["patient_id"] for item in verification if all(result["status"] == "verified" for result in item["criteria"])]
    excluded = [item["patient_id"] for item in verification if item["patient_id"] not in included]
    return {"verification_results": verification, "evidence_items": evidence, "included_patient_ids": included, "excluded_patient_ids": excluded, "run_status": "validating_evidence", "current_node": "structured_fhir_verification", "updated_at": _utc()}


def evidence_validation(state: WorkflowState) -> dict[str, Any]:
    _node_started(state, "evidence_validation")
    required = {item["criterion_id"] for item in state["structured_plan"]["criteria"] if item.get("required", True)}
    errors: list[str] = []
    for patient in state.get("included_patient_ids", []):
        rows = [item for item in state["evidence_items"] if item["patient_id"] == patient]
        if {item["criterion_id"] for item in rows} != required:
            errors.append(f"patient {patient} does not have evidence for every required criterion")
        if any(item["verification_status"] != "verified" or not item.get("source_fhir_resource_id") for item in rows):
            errors.append(f"patient {patient} has unsupported or unproven evidence")
    if errors:
        return _fail({**state, "errors": list(state.get("errors", [])) + errors}, "failed")
    return {"run_status": "awaiting_approval", "current_node": "evidence_validation", "updated_at": _utc()}


def policy_postcheck(state: WorkflowState) -> dict[str, Any]:
    _node_started(state, "policy_postcheck")
    policy(state["run_id"], "postcheck", "allow", "All required criteria are verified with structured provenance.", {"included_count": len(state.get("included_patient_ids", []))})
    return {"run_status": "awaiting_approval", "current_node": "policy_postcheck", "updated_at": _utc()}


def prepare_approval(state: WorkflowState) -> dict[str, Any]:
    _node_started(state, "prepare_approval")
    payload = {"run_id": state["run_id"], "original_request": state["original_request"], "structured_plan": state["structured_plan"], "retrieval_attempts": state.get("retrieval_attempts", []), "retrieval_fallbacks": state.get("retrieval_fallbacks", []), "candidate_count": len(state.get("candidate_patient_ids", [])), "included_patient_ids": state.get("included_patient_ids", []), "excluded_patient_ids": state.get("excluded_patient_ids", []), "evidence_summaries": [{key: item.get(key) for key in ("patient_id", "criterion_id", "verification_status", "source_fhir_resource_id", "explanation")} for item in state.get("evidence_items", [])], "warnings": state.get("warnings", []), "policy_reason": "Cohort finalization requires reviewer approval.", "requested_reviewer_actions": ["approve", "reject", "request_changes", "cancel"]}
    approval_id = create_approval(state["run_id"], state["actor_context"]["actor_id"], payload)
    update_run(state["run_id"], approval_id=approval_id, status="awaiting_approval")
    event(state["run_id"], state["run_id"], "awaiting_approval", "prepare_approval", {"approval_id": approval_id, "included_count": len(state.get("included_patient_ids", []))})
    return {"approval_id": approval_id, "run_status": "awaiting_approval", "current_node": "prepare_approval", "updated_at": _utc()}


def human_approval(state: WorkflowState) -> dict[str, Any]:
    if not get_settings().agent_execution_enabled:
        policy(state["run_id"], "kill_switch", "deny", "Platform kill switch disabled continuation before approval.")
        return _fail(state, "Platform kill switch disabled continuation before approval.")
    payload = {"run_id": state["run_id"], "original_request": state["original_request"], "structured_plan": state["structured_plan"], "retrieval_providers_used": [item.get("provider") for item in state.get("retrieval_attempts", []) if item.get("status") == "success"], "fallback_events": state.get("retrieval_fallbacks", []), "candidate_count": len(state.get("candidate_patient_ids", [])), "proposed_included_patients": state.get("included_patient_ids", []), "proposed_excluded_patients": state.get("excluded_patient_ids", []), "criterion_level_evidence_summaries": [{"patient_id": item["patient_id"], "criterion_id": item["criterion_id"], "status": item["verification_status"], "source_fhir_resource_id": item.get("source_fhir_resource_id")} for item in state.get("evidence_items", [])], "warnings": state.get("warnings", []), "policy_reason": "Reviewer approval is required before cohort finalization.", "requested_reviewer_actions": ["approve", "reject", "request_changes", "cancel"]}
    decision = interrupt(payload)
    if not isinstance(decision, dict):
        return _fail(state, "approval decision payload is invalid")
    return {"approval_decision": decision, "approval_status": str(decision.get("decision", "unknown")), "current_node": "human_approval", "updated_at": _utc()}


def finalize_result(state: WorkflowState) -> dict[str, Any]:
    decision = state.get("approval_decision", {})
    if decision.get("decision") != "approve":
        return _fail(state, "finalization attempted without approval")
    if existing_decision(state["approval_id"]) is not None:
        return _fail(state, "duplicate or conflicting approval decision")
    with SessionLocal.begin() as session:
        session.add(ApprovalDecision(id=str(uuid4()), approval_id=state["approval_id"], run_id=state["run_id"], actor_id=str(decision.get("actor_id")), actor_role=str(decision.get("actor_role")), decision="approve", comment=decision.get("comment")))
        approval = session.get(ApprovalRequest, state["approval_id"])
        if approval is not None:
            approval.status = "approved"
            approval.decided_at = datetime.now(UTC)
    event(state["run_id"], state["run_id"], "approved", "finalize_result", {"approval_id": state["approval_id"]})
    result = {"included_patient_ids": state.get("included_patient_ids", []), "excluded_patient_ids": state.get("excluded_patient_ids", []), "evidence_count": len(state.get("evidence_items", [])), "approval_id": state["approval_id"], "synthetic_data_notice": "Synthetic Synthea data only.", "clinical_validation_notice": "Not clinically validated."}
    return {"final_result": result, "run_status": "completed", "current_node": "finalize_result", "updated_at": _utc()}


def reject_result(state: WorkflowState) -> dict[str, Any]:
    decision = state.get("approval_decision", {})
    if existing_decision(state["approval_id"]) is None:
        with SessionLocal.begin() as session:
            session.add(ApprovalDecision(id=str(uuid4()), approval_id=state["approval_id"], run_id=state["run_id"], actor_id=str(decision.get("actor_id")), actor_role=str(decision.get("actor_role")), decision=str(decision.get("decision")), comment=decision.get("comment")))
            approval = session.get(ApprovalRequest, state["approval_id"])
            if approval is not None:
                approval.status = "changes_requested" if decision.get("decision") == "request_changes" else "rejected"
                approval.decided_at = datetime.now(UTC)
    status = "needs_clarification" if decision.get("decision") == "request_changes" else "rejected"
    event(state["run_id"], state["run_id"], "rejected" if status == "rejected" else "request_changes", "reject_result", {"decision": decision.get("decision")})
    return {"run_status": status, "current_node": "reject_result", "final_result": {"approval_id": state["approval_id"], "decision": decision.get("decision"), "comment": decision.get("comment"), "synthetic_data_notice": "Synthetic Synthea data only."}, "updated_at": _utc()}


def cancel_run(state: WorkflowState) -> dict[str, Any]:
    decision = state.get("approval_decision", {})
    if existing_decision(state["approval_id"]) is None:
        with SessionLocal.begin() as session:
            session.add(ApprovalDecision(id=str(uuid4()), approval_id=state["approval_id"], run_id=state["run_id"], actor_id=str(decision.get("actor_id")), actor_role=str(decision.get("actor_role")), decision="cancel", comment=decision.get("comment")))
            approval = session.get(ApprovalRequest, state["approval_id"])
            if approval is not None:
                approval.status = "cancelled"
                approval.decided_at = datetime.now(UTC)
    event(state["run_id"], state["run_id"], "cancelled", "cancel_run")
    return {"run_status": "cancelled", "current_node": "cancel_run", "final_result": {"approval_id": state["approval_id"], "cancelled": True, "synthetic_data_notice": "Synthetic Synthea data only."}, "updated_at": _utc()}


def fail_safely(state: WorkflowState) -> dict[str, Any]:
    event(state["run_id"], state["run_id"], "failed", state.get("current_node"), {"errors": state.get("errors", [])})
    return {"run_status": state.get("run_status", "failed"), "current_node": "fail_safely", "final_result": {"errors": state.get("errors", []), "synthetic_data_notice": "Synthetic Synthea data only."}, "updated_at": _utc()}


def record_completion(state: WorkflowState) -> dict[str, Any]:
    status = state.get("run_status", "failed")
    update_run(state["run_id"], status=status, current_node="record_completion", completed_at=datetime.now(UTC) if status in {"completed", "rejected", "cancelled", "failed", "needs_clarification"} else None, final_result=state.get("final_result"), warnings=state.get("warnings", []), errors=state.get("errors", []))
    event(state["run_id"], state["run_id"], status, "record_completion", {"status": status})
    return {"current_node": "record_completion", "updated_at": _utc()}


def _after_create(state: WorkflowState) -> str:
    return "validate_plan" if state.get("structured_plan") else "record_completion"


def _after_intake(state: WorkflowState) -> str:
    return "create_plan" if state.get("run_status") == "planning" else "fail_safely"


def _after_validate(state: WorkflowState) -> str:
    return "policy_precheck" if state.get("run_status") == "validating_plan" and not state.get("errors") else "fail_safely"


def _after_precheck(state: WorkflowState) -> str:
    return "retrieve_candidates" if state.get("run_status") == "retrieving" else "fail_safely"


def _after_retrieve(state: WorkflowState) -> str:
    return "structured_fhir_verification" if state.get("run_status") == "verifying" else "fail_safely"


def _after_evidence(state: WorkflowState) -> str:
    return "policy_postcheck" if state.get("run_status") == "awaiting_approval" else "fail_safely"


def _after_approval(state: WorkflowState) -> str:
    decision = state.get("approval_decision", {}).get("decision")
    return {"approve": "finalize_result", "reject": "reject_result", "request_changes": "reject_result", "cancel": "cancel_run"}.get(str(decision), "fail_safely")


def build_graph(checkpointer: BaseCheckpointSaver[str]) -> Any:
    graph = StateGraph(WorkflowState)
    for name, function in (("intake", intake), ("create_plan", create_plan), ("validate_plan", validate_plan), ("policy_precheck", policy_precheck), ("retrieve_candidates", retrieve_candidates), ("structured_fhir_verification", structured_fhir_verification), ("evidence_validation", evidence_validation), ("policy_postcheck", policy_postcheck), ("prepare_approval", prepare_approval), ("human_approval", human_approval), ("finalize_result", finalize_result), ("reject_result", reject_result), ("cancel_run", cancel_run), ("fail_safely", fail_safely), ("record_completion", record_completion)):
        graph.add_node(name, function)
    graph.add_edge(START, "intake")
    graph.add_conditional_edges("intake", _after_intake)
    graph.add_conditional_edges("create_plan", _after_create)
    graph.add_conditional_edges("validate_plan", _after_validate)
    graph.add_conditional_edges("policy_precheck", _after_precheck)
    graph.add_conditional_edges("retrieve_candidates", _after_retrieve)
    graph.add_edge("structured_fhir_verification", "evidence_validation")
    graph.add_conditional_edges("evidence_validation", _after_evidence)
    graph.add_edge("policy_postcheck", "prepare_approval")
    graph.add_edge("prepare_approval", "human_approval")
    graph.add_conditional_edges("human_approval", _after_approval)
    for name in ("finalize_result", "reject_result", "cancel_run", "fail_safely"):
        graph.add_edge(name, "record_completion")
    graph.add_edge("record_completion", END)
    return graph.compile(checkpointer=checkpointer)
