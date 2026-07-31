"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

type Json = Record<string, unknown>;
const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export default function PerformancePage() {
  const [policy, setPolicy] = useState<Json | null>(null);
  const [history, setHistory] = useState<Json | null>(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    Promise.all([
      fetch(`${apiBase}/api/v1/performance/policy`, { cache: "no-store" }).then((response) => { if (!response.ok) throw new Error("policy"); return response.json(); }),
      fetch(`${apiBase}/api/v1/performance`, { cache: "no-store" }).then((response) => { if (!response.ok) throw new Error("history"); return response.json(); }),
    ]).then(([policyResult, historyResult]) => { setPolicy(policyResult); setHistory(historyResult); }).catch(() => setError(true));
  }, []);
  const items = Array.isArray(history?.items) ? history.items as Json[] : [];
  const gates = (policy?.blocking_correctness_gates ?? {}) as Record<string, unknown>;
  return <main className="min-h-screen px-5 py-8 sm:px-8 lg:px-12"><div className="mx-auto max-w-6xl">
    <Link className="text-sm font-semibold text-teal" href="/">← Overview</Link>
    <p className="mt-8 text-sm font-semibold uppercase tracking-[0.18em] text-teal">Performance &amp; Reliability</p>
    <h1 className="mt-2 text-3xl font-bold text-ink">Bounded local engineering measurements</h1>
    <div className="mt-5 rounded-2xl border border-amber-200 bg-amber-50 p-5 text-sm text-amber-950"><strong>Synthetic development evaluation.</strong> Results are local-hardware-specific, not clinically validated, and not production capacity evidence. Execution is CLI-controlled.</div>
    {error && <div role="alert" className="mt-6 rounded-2xl bg-red-50 p-5 text-red-800">Performance data is unavailable or this account lacks evaluation access.</div>}
    <section className="mt-8 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"><h2 className="text-xl font-bold">Correctness gates</h2><div className="mt-4 grid gap-3 md:grid-cols-3">{Object.entries(gates).map(([name, value]) => <div key={name} className="rounded-xl bg-slate-50 p-4 text-sm"><p className="font-semibold">{name}</p><p className="mt-1 text-slate-600">Required: {String(value)}</p><p className="mt-2 text-xs text-emerald-700">Blocking control</p></div>)}</div></section>
    <section className="mt-8"><h2 className="text-xl font-bold">Recent executions</h2>{items.length === 0 ? <div className="mt-4 rounded-2xl border border-dashed border-slate-300 p-6 text-sm text-slate-500">No performance executions have been recorded. Run a bounded CLI profile to populate this view.</div> : <div className="mt-4 overflow-x-auto rounded-2xl border border-slate-200 bg-white shadow-sm"><table className="min-w-full text-left text-sm"><thead className="bg-slate-50 text-xs uppercase text-slate-500"><tr>{["Execution", "Profile", "Status", "Dataset", "Created"].map((heading) => <th className="px-4 py-3" key={heading}>{heading}</th>)}</tr></thead><tbody>{items.map((item) => <tr className="border-t border-slate-100" key={String(item.execution_id)}><th className="px-4 py-3 font-medium">{String(item.execution_id)}</th><td className="px-4 py-3">{String(item.profile_id)}</td><td className="px-4 py-3">{String(item.status)}</td><td className="px-4 py-3">{String(item.dataset_id ?? "synthetic")}</td><td className="px-4 py-3">{String(item.created_at ?? "—")}</td></tr>)}</tbody></table></div>}</section>
    <section className="mt-8 grid gap-4 md:grid-cols-3"><a className="rounded-2xl border border-slate-200 bg-white p-5 text-sm shadow-sm hover:border-teal" href="http://127.0.0.1:3000">Grafana dashboards<span className="mt-1 block text-slate-500">Operational charts are local-only.</span></a><a className="rounded-2xl border border-slate-200 bg-white p-5 text-sm shadow-sm hover:border-teal" href="/release-evaluations">Release evaluations<span className="mt-1 block text-slate-500">Performance references remain informational by default.</span></a><Link className="rounded-2xl border border-slate-200 bg-white p-5 text-sm shadow-sm hover:border-teal" href="/observability">Observability<span className="mt-1 block text-slate-500">Trace and service summaries.</span></Link></section>
  </div></main>;
}
