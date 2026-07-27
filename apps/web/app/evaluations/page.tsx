"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";

type Profile = { metrics: Record<string, number>; category_metrics?: Record<string, Record<string, number>>; reranking_outcomes?: Record<string, number> };
type Case = { query_id: string; query: string; category: string; expected_patient_ids: string[]; first_stage_results: string[]; reranked_results: string[]; structured_evidence: string; likely_failure_reason: string };
type Evaluation = { dataset_id: string; evaluation_case_count?: number; profiles: Record<string, Profile>; failure_analysis?: Case[]; synthetic_development_evaluation: boolean; not_clinically_validated: boolean };
const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export default function EvaluationsPage() {
  const [evaluation, setEvaluation] = useState<Evaluation | null>(null);
  const [error, setError] = useState(false);
  const [category, setCategory] = useState("all");
  useEffect(() => { fetch(`${apiBase}/api/v1/evaluations/phase2-6-bounded`, { cache: "no-store" }).then((response) => { if (!response.ok) throw new Error("unavailable"); return response.json() as Promise<Evaluation>; }).then(setEvaluation).catch(() => setError(true)); }, []);
  const profiles = evaluation?.profiles ?? {};
  const categories = useMemo(() => ["all", ...new Set((evaluation?.failure_analysis ?? []).map((item) => item.category))], [evaluation]);
  const failures = (evaluation?.failure_analysis ?? []).filter((item) => category === "all" || item.category === category);
  return <main className="min-h-screen px-5 py-8 sm:px-8 lg:px-12"><div className="mx-auto max-w-6xl">
    <Link className="text-sm font-semibold text-teal" href="/">← Overview</Link>
    <p className="mt-8 text-sm font-semibold uppercase tracking-[0.18em] text-teal">Evaluations</p>
    <h1 className="mt-2 text-3xl font-bold text-ink">Retrieval quality and latency</h1>
    <div className="mt-5 rounded-2xl border border-amber-200 bg-amber-50 p-5 text-sm text-amber-950"><strong>Synthetic development evaluation.</strong> Results are not clinically validated and are not production performance.</div>
    {error && <div role="alert" className="mt-6 rounded-2xl bg-red-50 p-5 text-red-800">Evaluation results are unavailable. Run the backend evaluation first.</div>}
    {!error && !evaluation && <p className="mt-8 text-slate-500">Loading measured results…</p>}
    {evaluation && <><p className="mt-6 text-sm text-slate-600">Dataset: <code>{evaluation.dataset_id}</code> · {evaluation.evaluation_case_count ?? "—"} structured-ground-truth cases · same bounded clinical documents.</p><div className="mt-6 overflow-x-auto rounded-2xl border border-slate-200 bg-white shadow-sm"><table className="min-w-full text-left text-sm"><thead className="bg-slate-50 text-xs uppercase text-slate-500"><tr>{["Profile","P@5","R@5","MRR","nDCG@5","Zero-result","Median ms","P95 ms"].map((heading) => <th key={heading} className="px-4 py-3">{heading}</th>)}</tr></thead><tbody>{Object.entries(profiles).map(([name, value]) => <tr key={name} className="border-t border-slate-100"><th className="px-4 py-4 font-semibold text-ink">{name}</th><td className="px-4 py-4">{value.metrics.precision_at_5?.toFixed(3)}</td><td className="px-4 py-4">{value.metrics.recall_at_5?.toFixed(3)}</td><td className="px-4 py-4">{value.metrics.mrr?.toFixed(3)}</td><td className="px-4 py-4">{value.metrics.ndcg_at_5?.toFixed(3)}</td><td className="px-4 py-4">{value.metrics.zero_result_rate?.toFixed(3)}</td><td className="px-4 py-4">{value.metrics.median_latency_ms?.toFixed(2)}</td><td className="px-4 py-4">{value.metrics.p95_latency_ms?.toFixed(2)}</td></tr>)}</tbody></table></div><section className="mt-8"><div className="flex items-center justify-between"><h2 className="text-xl font-bold text-ink">Failure analysis</h2><label className="text-sm text-slate-600">Category <select aria-label="Filter failure analysis by category" className="ml-2 rounded border border-slate-300 px-2 py-1" value={category} onChange={(event) => setCategory(event.target.value)}>{categories.map((item) => <option key={item}>{item}</option>)}</select></label></div><div className="mt-4 grid gap-4">{failures.map((item) => <article key={item.query_id} className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"><p className="font-semibold text-ink">{item.query}</p><p className="mt-2 text-sm text-slate-600">{item.category} · expected {item.expected_patient_ids.join(", ")}</p><p className="mt-2 text-sm">First stage: {item.first_stage_results.join(", ") || "no results"}</p><p className="text-sm">Reranked: {item.reranked_results.join(", ") || "no results"}</p><p className="mt-2 text-sm text-slate-600">{item.structured_evidence} {item.likely_failure_reason}</p></article>)}</div></section></>}
  </div></main>;
}
