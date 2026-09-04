export type Role = "researcher" | "reviewer" | "governance_officer" | "platform_operator" | "auditor" | "administrator";

export type User = { display_name: string; role: Role; actor_id?: string; permissions?: string[] };
export type Dataset = { id: string; name: string; imported_patient_count?: number; status?: string; synthetic?: boolean };
export type Run = {
  run_id: string;
  thread_id?: string;
  status: string;
  current_node?: string;
  created_at?: string;
  updated_at?: string;
  dataset_id?: string;
  actor_id?: string;
  actor_role?: string;
  approval_id?: string;
  structured_plan?: Record<string, unknown> | null;
  final_result?: Record<string, unknown> | null;
  warnings?: string[];
  errors?: string[];
  planner_lineage?: Record<string, unknown> | null;
  synthetic_data_notice?: string;
  links?: Record<string, string>;
};
export type ApiList<T> = { items: T[]; page?: number; page_size?: number };
export type Candidate = { patient_id?: string; included?: boolean; verification_status?: string; retrieval_provider?: string; retrieval_score?: number; document_ids?: string[] };
export type Evidence = { patient_id?: string; criterion_id?: string; criterion_description?: string; verification_status?: string; structured_value?: Record<string, unknown>; source_resource_type?: string; source_fhir_resource_id?: string; explanation?: string; verification_tool?: string };
export type Approval = { id: string; run_id?: string; requested_by_actor_id?: string; status?: string; payload?: Record<string, unknown>; created_at?: string; decided_at?: string };

export class ApiError extends Error {
  status: number;
  detail: string;
  constructor(status: number, detail: string) { super(detail); this.status = status; this.detail = detail; }
}

const apiBase = "/backend";
export { apiBase };

function record(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function stringValue(value: unknown): string | undefined { return typeof value === "string" ? value : undefined; }

export function asList<T>(value: unknown, itemAdapter: (item: unknown) => T | null): T[] {
  const source = Array.isArray(value) ? value : record(value).items ?? record(value).data ?? record(value).results ?? [];
  return Array.isArray(source) ? source.map(itemAdapter).filter((item): item is T => item !== null) : [];
}

export function adaptDataset(value: unknown): Dataset[] {
  return asList(value, (item) => {
    const row = record(item); const id = stringValue(row.id);
    return id ? { id, name: stringValue(row.name) ?? id, imported_patient_count: typeof row.imported_patient_count === "number" ? row.imported_patient_count : undefined, status: stringValue(row.status), synthetic: row.synthetic !== false } : null;
  });
}

export function adaptRun(value: unknown): Run | null {
  const row = record(value); const runId = stringValue(row.run_id) ?? stringValue(row.id);
  return runId ? { run_id: runId, thread_id: stringValue(row.thread_id), status: stringValue(row.status) ?? "unknown", current_node: stringValue(row.current_node), created_at: stringValue(row.created_at), updated_at: stringValue(row.updated_at), dataset_id: stringValue(row.dataset_id), actor_id: stringValue(row.actor_id), actor_role: stringValue(row.actor_role), approval_id: stringValue(row.approval_id), structured_plan: record(row.structured_plan), final_result: row.final_result && typeof row.final_result === "object" ? record(row.final_result) : null, warnings: Array.isArray(row.warnings) ? row.warnings.filter((x): x is string => typeof x === "string") : [], errors: Array.isArray(row.errors) ? row.errors.filter((x): x is string => typeof x === "string") : [], planner_lineage: row.planner_lineage && typeof row.planner_lineage === "object" ? record(row.planner_lineage) : null, synthetic_data_notice: stringValue(row.synthetic_data_notice), links: record(row.links) as Record<string, string> } : null;
}

export function adaptRunList(value: unknown): ApiList<Run> { return { items: asList(value, adaptRun) }; }
export function adaptCandidates(value: unknown): Candidate[] { return asList(value, (item) => { const row = record(item); return stringValue(row.patient_id) ? { patient_id: stringValue(row.patient_id), included: row.included === true, verification_status: stringValue(row.verification_status), retrieval_provider: stringValue(row.retrieval_provider), retrieval_score: typeof row.retrieval_score === "number" ? row.retrieval_score : undefined, document_ids: Array.isArray(row.document_ids) ? row.document_ids.filter((x): x is string => typeof x === "string") : [] } : null; }); }
export function adaptEvidence(value: unknown): Evidence[] { return asList(value, (item) => { const row = record(item); return stringValue(row.patient_id) ? { patient_id: stringValue(row.patient_id), criterion_id: stringValue(row.criterion_id), criterion_description: stringValue(row.criterion_description), verification_status: stringValue(row.verification_status), structured_value: record(row.structured_value), source_resource_type: stringValue(row.source_resource_type), source_fhir_resource_id: stringValue(row.source_fhir_resource_id), explanation: stringValue(row.explanation), verification_tool: stringValue(row.verification_tool) } : null; }); }
export function adaptApproval(value: unknown): Approval | null { const row = record(value); const id = stringValue(row.id); return id ? { id, run_id: stringValue(row.run_id), requested_by_actor_id: stringValue(row.requested_by_actor_id), status: stringValue(row.status), payload: record(row.payload), created_at: stringValue(row.created_at), decided_at: stringValue(row.decided_at) } : null; }
export function adaptApprovalList(value: unknown): ApiList<Approval> { return { items: asList(value, adaptApproval) }; }

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.delete("x-actor-id");
  headers.delete("x-actor-role");
  if (!headers.get("authorization")?.trim()) headers.delete("authorization");
  let response: Response;
  try { response = await fetch(`${apiBase}${path}`, { ...init, headers, credentials: "include", cache: "no-store" }); }
  catch { throw new ApiError(0, "The request could not reach the API."); }
  const text = await response.text(); let body: unknown = null;
  try { body = text ? JSON.parse(text) : null; } catch { body = null; }
  if (response.status === 401) throw new ApiError(401, "Your session has expired. Sign in again.");
  if (response.status === 403) throw new ApiError(403, "You do not have permission to perform this action.");
  if (response.status === 422) throw new ApiError(422, validationMessage(body));
  if (response.status >= 500) throw new ApiError(response.status, "The backend encountered an error.");
  if (!response.ok) throw new ApiError(response.status, stringValue(record(body).detail) ?? `Request failed (${response.status}).`);
  return body as T;
}

export function explainError(error: unknown): string { return error instanceof ApiError ? error.detail : "The response was not valid. Please retry or contact the platform operator."; }

function validationMessage(body: unknown): string {
  const detail = record(body).detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    const messages = detail.flatMap((item) => {
      const message = record(item).msg;
      return typeof message === "string" && message.trim() ? [message] : [];
    });
    if (messages.length) return messages.join(" ");
  }
  return "The submitted data is invalid.";
}
