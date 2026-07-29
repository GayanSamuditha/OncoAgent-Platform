"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";

const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
type Json = Record<string, unknown>;

export default function CrewAIPage() {
  const [status, setStatus] = useState<Json | null>(null);
  const [dataset, setDataset] = useState("");
  const [question, setQuestion] = useState("Find synthetic adults with hypertension and elevated blood pressure.");
  const [run, setRun] = useState<Json | null>(null);
  const [output, setOutput] = useState<Json | null>(null);
  const [temporal, setTemporal] = useState<Json | null>(null);
  const [message, setMessage] = useState("");
  const temporalWorkflow = (temporal?.workflow as Json | undefined) ?? {};
  const temporalUiUrl = typeof temporal?.ui_url === "string" ? temporal.ui_url : "";

  useEffect(() => {
    fetch(`${apiBase}/api/v1/crews/oncology-research/status`, { credentials: "include" })
      .then((response) => { if (!response.ok) throw new Error("CrewAI status unavailable."); return response.json(); })
      .then(setStatus).catch(() => setMessage("CrewAI status unavailable."));
  }, []);

  useEffect(() => {
    const runId = typeof run?.run_id === "string" ? run.run_id : undefined;
    if (!runId) return;
    const timer = window.setInterval(() => {
      fetch(`${apiBase}/api/v1/crews/oncology-research/runs/${runId}`, { credentials: "include" })
        .then((response) => response.json()).then(setRun).catch(() => setMessage("Run status unavailable."));
      fetch(`${apiBase}/api/v1/crews/oncology-research/runs/${runId}/output`, { credentials: "include" })
        .then((response) => response.ok ? response.json() : null).then((value) => { if (value) setOutput(value.output ?? value); });
      fetch(`${apiBase}/api/v1/crews/oncology-research/runs/${runId}/temporal`, { credentials: "include" })
        .then((response) => response.ok ? response.json() : null).then(setTemporal);
    }, 2000);
    return () => window.clearInterval(timer);
  }, [run]);

  async function submit(event: FormEvent) {
    event.preventDefault(); setMessage("Starting bounded downstream crew…");
    try {
      const response = await fetch(`${apiBase}/api/v1/crews/oncology-research/runs`, {
        method: "POST", credentials: "include", headers: { "content-type": "application/json" },
        body: JSON.stringify({ dataset_id: dataset, research_question: question,
          structured_criteria: [{ criterion_type: "condition", clinical_concept: "hypertension", required: true },
            { criterion_type: "observation", clinical_concept: "elevated blood pressure", required: true }],
          maximum_candidates: 20, retrieval_profile: "medcpt", model_profile: "automatic",
          actor_context: { actor_id: "researcher-console", actor_role: "researcher" } }),
      });
      const body = await response.json(); if (!response.ok) throw new Error(body.detail ?? "CrewAI run failed");
      setRun(body); setOutput(null); setMessage(`Run ${String(body.run_id)} started; execution stops for human review.`);
    } catch (error) { setMessage(error instanceof Error ? error.message : "CrewAI run failed."); }
  }

  async function review(decision: "accept_for_synthetic_research" | "reject" | "request_changes") {
    if (!run?.run_id) return;
    const response = await fetch(`${apiBase}/api/v1/crews/oncology-research/runs/${run.run_id}/review`, {
      method: "POST", credentials: "include", headers: { "content-type": "application/json" },
      body: JSON.stringify({ decision, comment: "Reviewed for synthetic development use." }),
    });
    const body = await response.json(); setMessage(response.ok ? `Review recorded: ${decision}.` : String(body.detail ?? "Review failed."));
    if (response.ok) setRun((current) => current ? { ...current, status: body.status } : current);
  }

  return <main className="min-h-screen px-5 py-8 sm:px-8 lg:px-12"><div className="mx-auto max-w-6xl">
    <Link className="text-sm font-semibold text-teal" href="/agent-catalog">← Agent Catalog</Link>
    <p className="mt-8 text-sm font-semibold uppercase tracking-[0.18em] text-teal">Downstream application</p>
    <h1 className="mt-2 text-3xl font-bold text-ink">CrewAI Oncology Research Crew</h1>
    <p className="mt-3 text-slate-600">Sequential CrewAI collaboration through the governed MCP gateway. CrewAI cannot access PostgreSQL, FHIR repositories, or approve its own output.</p>
    <div className="mt-6 rounded-2xl border border-amber-200 bg-amber-50 p-5 text-sm text-amber-950"><strong>Synthetic development use only.</strong> Only synthetic Synthea data is supported; this output is not clinically validated. Development identity simulation is not production authentication.</div>
    <section className="mt-6 grid gap-5 md:grid-cols-2"><article className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"><h2 className="font-semibold">Runtime status</h2><dl className="mt-4 grid gap-2 text-sm"><div><dt className="font-semibold">Enabled</dt><dd>{String(status?.enabled ?? "Loading…")}</dd></div><div><dt className="font-semibold">CrewAI</dt><dd>{String(status?.crewai_version ?? "—")}</dd></div><div><dt className="font-semibold">Local model</dt><dd>{String(status?.default_model ?? "—")}</dd></div><div><dt className="font-semibold">MCP gateway</dt><dd>{String(status?.mcp_url ?? "—")}</dd></div><div><dt className="font-semibold">Execution mode</dt><dd>{String(status?.execution_mode ?? "—")}</dd></div><div><dt className="font-semibold">Temporal</dt><dd>{String(status?.temporal_address ?? "disabled")}</dd></div></dl></article><article className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"><h2 className="font-semibold">Sequential pipeline</h2><ol className="mt-4 list-decimal space-y-2 pl-5 text-sm"><li>Cohort Researcher — search only</li><li>Structured Evidence Investigator — MCP facts</li><li>Eligibility Evidence Reviewer — provenance checks</li><li>Research Brief Writer — no tools, review-ready brief</li></ol><p className="mt-4 text-xs text-slate-500">Temporal durably coordinates the lifecycle; the four-agent CrewAI sequence remains unchanged.</p></article></section>
    <form onSubmit={submit} className="mt-6 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"><label htmlFor="dataset" className="block text-sm font-semibold">Dataset ID</label><input id="dataset" required className="mt-2 w-full rounded border border-slate-300 p-3" value={dataset} onChange={(e) => setDataset(e.target.value)} /><label htmlFor="question" className="mt-4 block text-sm font-semibold">Research question</label><textarea id="question" required className="mt-2 min-h-28 w-full rounded border border-slate-300 p-3" value={question} onChange={(e) => setQuestion(e.target.value)} /><button className="mt-4 rounded bg-teal px-5 py-3 font-semibold text-white" type="submit">Run downstream crew</button>{message && <p role="status" className="mt-4 text-sm text-slate-700">{message}</p>}</form>
    {run && <section className="mt-6 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"><h2 className="font-semibold">Live run</h2><dl className="mt-4 grid gap-2 text-sm sm:grid-cols-3"><div><dt className="font-semibold">Run ID</dt><dd className="break-all">{String(run.run_id ?? run.id)}</dd></div><div><dt className="font-semibold">Status</dt><dd>{String(run.status)}</dd></div><div><dt className="font-semibold">Current task</dt><dd>{String(run.current_task ?? temporalWorkflow.current_stage ?? "—")}</dd></div><div><dt className="font-semibold">Temporal workflow</dt><dd className="break-all">{String(run.temporal_workflow_id ?? "—")}</dd></div><div><dt className="font-semibold">Activity attempt</dt><dd>{String(temporalWorkflow.activity_attempt ?? run.temporal_activity_attempt ?? "—")}</dd></div><div><dt className="font-semibold">Safe heartbeat</dt><dd>{String(run.temporal_last_heartbeat_at ?? "—")}</dd></div></dl>{temporalUiUrl && <p className="mt-3 text-sm"><a className="font-semibold text-teal" href={temporalUiUrl} target="_blank" rel="noreferrer">Open Temporal UI</a></p>}{String(run.status) === "awaiting_human_review" && <div className="mt-5 flex flex-wrap gap-2"><button className="rounded bg-teal px-3 py-2 text-sm font-semibold text-white" onClick={() => review("accept_for_synthetic_research")}>Accept for synthetic research</button><button className="rounded border border-slate-300 px-3 py-2 text-sm font-semibold" onClick={() => review("request_changes")}>Request changes</button><button className="rounded border border-rose-300 px-3 py-2 text-sm font-semibold text-rose-700" onClick={() => review("reject")}>Reject</button></div>}{output && <div className="mt-5 rounded-lg bg-slate-50 p-4 text-sm"><h3 className="font-semibold">Structured brief</h3><p className="mt-2">Candidates: {String(output.candidate_count ?? 0)} · Proposed included: {String(output.proposed_included_count ?? 0)} · Review: {String(output.review_status ?? "—")}</p><p className="mt-2">{String(output.synthetic_data_notice ?? "")}</p><p>{String(output.clinical_validation_notice ?? "")}</p></div>}</section>}
  </div></main>;
}
