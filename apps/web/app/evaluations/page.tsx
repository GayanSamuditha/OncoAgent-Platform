"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";

const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
type Json = Record<string, unknown>;

export default function EvaluationsPage() {
  const [retrieval, setRetrieval] = useState<Json | null>(null);
  const [cross, setCross] = useState<Json | null>(null);
  const [policy, setPolicy] = useState<Json | null>(null);
  const [agents, setAgents] = useState<Json | null>(null);
  const [error, setError] = useState(false);
  const [framework, setFramework] = useState("all");
  useEffect(() => {
    Promise.all([
      fetch(`${apiBase}/api/v1/evaluations/phase2-6-bounded`, { cache: "no-store" }).then((r) => r.json()),
      fetch(`${apiBase}/api/v1/evaluations/cross-framework`, { cache: "no-store" }).then((r) => r.json()),
      fetch(`${apiBase}/api/v1/framework-policy`, { cache: "no-store" }).then((r) => r.json()),
      fetch(`${apiBase}/api/v1/agents`, { headers: { "X-Actor-Id": "evaluation-console", "X-Actor-Role": "admin" } }).then((r) => r.json()),
    ]).then(([retrievalResult, crossResult, policyResult, agentResult]) => { setRetrieval(retrievalResult); setCross(crossResult); setPolicy(policyResult); setAgents(agentResult); }).catch(() => setError(true));
  }, []);
  const profiles = (retrieval?.profiles ?? {}) as Record<string, Json>;
  const frameworks = (cross?.frameworks ?? {}) as Record<string, Json>;
  const visibleFrameworks = Object.entries(frameworks).filter(([name]) => framework === "all" || name === framework);
  const agentItems = (agents?.items ?? []) as Json[];
  const policyFrameworks = (policy?.frameworks ?? {}) as Record<string, Json>;
  const crossResults = Array.isArray(cross?.results) ? (cross?.results as Json[]) : [];
  const categories = useMemo(() => ["all", ...new Set(((cross?.results ?? []) as Json[]).map((item) => String(item.category ?? "unknown")))], [cross]);
  const [category, setCategory] = useState("all");
  return <main className="min-h-screen px-5 py-8 sm:px-8 lg:px-12"><div className="mx-auto max-w-6xl">
    <Link className="text-sm font-semibold text-teal" href="/">← Overview</Link><p className="mt-8 text-sm font-semibold uppercase tracking-[0.18em] text-teal">Evaluations</p><h1 className="mt-2 text-3xl font-bold text-ink">Retrieval and framework governance</h1>
    <div className="mt-5 rounded-2xl border border-amber-200 bg-amber-50 p-5 text-sm text-amber-950"><strong>Synthetic development evaluation.</strong> Results are local-hardware-specific, not clinically validated, and not production performance. The frameworks serve different architectural purposes; this page does not declare a universal winner.</div>
    {error && <div role="alert" className="mt-6 rounded-2xl bg-red-50 p-5 text-red-800">Evaluation results are unavailable.</div>}
    {retrieval && <section className="mt-6"><h2 className="text-xl font-bold text-ink">Retrieval evaluation</h2><p className="mt-2 text-sm text-slate-600">Dataset: {String(retrieval.dataset_id ?? "—")} · {String(retrieval.evaluation_case_count ?? "—")} structured cases</p><div className="mt-4 overflow-x-auto rounded-2xl border border-slate-200 bg-white shadow-sm"><table className="min-w-full text-left text-sm"><thead className="bg-slate-50 text-xs uppercase text-slate-500"><tr>{["Profile", "P@5", "Recall@5", "MRR", "nDCG@5", "Median ms"].map((h) => <th key={h} className="px-4 py-3">{h}</th>)}</tr></thead><tbody>{Object.entries(profiles).map(([name, value]) => { const metrics = (value.metrics ?? {}) as Json; return <tr key={name} className="border-t border-slate-100"><th className="px-4 py-3">{name}</th><td className="px-4 py-3">{Number(metrics.precision_at_5 ?? 0).toFixed(3)}</td><td className="px-4 py-3">{Number(metrics.recall_at_5 ?? 0).toFixed(3)}</td><td className="px-4 py-3">{Number(metrics.mrr ?? 0).toFixed(3)}</td><td className="px-4 py-3">{Number(metrics.ndcg_at_5 ?? 0).toFixed(3)}</td><td className="px-4 py-3">{Number(metrics.median_latency_ms ?? 0).toFixed(0)}</td></tr>; })}</tbody></table></div></section>}
    <section className="mt-10"><div className="flex flex-wrap items-center justify-between gap-3"><div><h2 className="text-xl font-bold text-ink">Cross-framework comparison</h2><p className="mt-2 text-sm text-slate-600">Shared scenarios: {String(cross?.scenario_count ?? "—")} · same synthetic dataset, criteria, candidate limit, and review policy.</p></div><label className="text-sm">Framework <select className="ml-2 rounded border border-slate-300 px-2 py-1" value={framework} onChange={(e) => setFramework(e.target.value)}><option value="all">All</option><option value="langgraph">LangGraph</option><option value="crewai">CrewAI</option></select></label></div><div className="mt-4 overflow-x-auto rounded-2xl border border-slate-200 bg-white shadow-sm"><table className="min-w-full text-left text-sm"><thead className="bg-slate-50 text-xs uppercase text-slate-500"><tr>{["Framework", "Completion", "Outcome match", "Provenance", "Review enforced", "Safety", "Median ms", "P95 ms", "Recovery"].map((h) => <th key={h} className="px-3 py-3">{h}</th>)}</tr></thead><tbody>{visibleFrameworks.map(([name, value]) => <tr key={name} className="border-t border-slate-100"><th className="px-3 py-3">{name}</th><td className="px-3 py-3">{(Number(value.completion_rate ?? 0) * 100).toFixed(1)}%</td><td className="px-3 py-3">{(Number(value.expected_outcome_match ?? 0) * 100).toFixed(1)}%</td><td className="px-3 py-3">{(Number(value.evidence_provenance_coverage ?? 0) * 100).toFixed(1)}%</td><td className="px-3 py-3">{(Number(value.human_review_enforcement ?? 0) * 100).toFixed(1)}%</td><td className="px-3 py-3">{(Number(value.safety_rejection_rate ?? 0) * 100).toFixed(1)}%</td><td className="px-3 py-3">{Number(value.median_latency_ms ?? 0).toFixed(0)}</td><td className="px-3 py-3">{Number(value.p95_latency_ms ?? 0).toFixed(0)}</td><td className="px-3 py-3">{String(value.recovery_capabilities ?? "—")}</td></tr>)}</tbody></table></div></section>
    <section className="mt-8 grid gap-5 md:grid-cols-2">{Object.entries(policyFrameworks).map(([name, value]) => <article key={name} className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"><h3 className="font-bold text-ink">{name === "langgraph" ? "Use LangGraph for governed operations" : "Use CrewAI for bounded downstream research"}</h3><p className="mt-2 text-sm text-slate-600">{String(value.justification)}</p><p className="mt-3 text-xs uppercase tracking-wide text-slate-500">Required controls</p><p className="mt-1 text-sm">{String((value.required_controls as string[] | undefined)?.join(" · ") ?? "—")}</p></article>)}</section>
    <section className="mt-8"><h2 className="text-xl font-bold text-ink">Unified agent registry</h2><div className="mt-4 grid gap-4 md:grid-cols-2">{agentItems.map((agent) => <article key={String(agent.agent_id)} className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"><h3 className="font-bold">{String(agent.name)}</h3><p className="mt-1 text-sm text-slate-600">{String(agent.framework)} · {String(agent.role)} · risk {String(agent.risk_tier)}</p><p className="mt-2 text-sm">Approval: {JSON.stringify(agent.approval_policy)} · Recovery: {JSON.stringify(agent.recovery)}</p></article>)}</div></section>
    {crossResults.length > 0 && <section className="mt-8"><div className="flex items-center justify-between"><h2 className="text-xl font-bold text-ink">Scenario-level comparison</h2><label className="text-sm">Scenario <select className="ml-2 rounded border border-slate-300 px-2 py-1" value={category} onChange={(e) => setCategory(e.target.value)}>{categories.map((item) => <option key={item}>{item}</option>)}</select></label></div><div className="mt-4 grid gap-3">{crossResults.filter((item) => category === "all" || String(item.category) === category).slice(0, 16).map((item, index) => <article key={`${String(item.scenario_id)}-${index}`} className="rounded-xl border border-slate-200 bg-white p-4 text-sm"><strong>{String(item.framework)}</strong> · {String(item.scenario_id)} · status {String(item.final_status)} · outcome match {String(item.expected_outcome_match)}</article>)}</div></section>}
  </div></main>;
}
