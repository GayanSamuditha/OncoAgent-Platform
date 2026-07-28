"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
type Json = Record<string, unknown>;

export default function ResiliencePage() {
  const [data, setData] = useState<Json | null>(null);
  const [catalog, setCatalog] = useState<Json | null>(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    Promise.all([
      fetch(`${apiBase}/api/v1/resilience/certifications`, { headers: { "X-Actor-Id": "resilience-console", "X-Actor-Role": "admin" }, cache: "no-store" }).then((r) => r.json()),
      fetch(`${apiBase}/api/v1/resilience/scenarios`, { headers: { "X-Actor-Id": "resilience-console", "X-Actor-Role": "admin" }, cache: "no-store" }).then((r) => r.json()),
    ]).then(([reports, scenarios]) => { setData(reports); setCatalog(scenarios); }).catch(() => setError(true));
  }, []);
  const reports = (data?.items ?? []) as Json[];
  const latest = reports[reports.length - 1];
  const scenarioItems = (catalog?.items ?? []) as Json[];
  const scenarioResults = (latest?.scenarios ?? []) as Json[];
  return <main className="min-h-screen px-5 py-8 sm:px-8 lg:px-12"><div className="mx-auto max-w-6xl">
    <Link className="text-sm font-semibold text-teal" href="/evaluations">← Evaluations</Link>
    <p className="mt-8 text-sm font-semibold uppercase tracking-[0.18em] text-teal">Resilience certification</p>
    <h1 className="mt-2 text-3xl font-bold text-ink">Temporal execution resilience</h1>
    <div className="mt-5 rounded-2xl border border-amber-200 bg-amber-50 p-5 text-sm text-amber-950"><strong>Local synthetic development validation.</strong> Fault controls are not exposed to the browser, are disabled by default, and this view is not clinical validation or production certification.</div>
    {error && <div role="alert" className="mt-6 rounded-2xl bg-red-50 p-5 text-red-800">Certification data is unavailable.</div>}
    {latest ? <><section className="mt-6 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"><p className="text-sm text-slate-600">Certification ID</p><p className="mt-1 font-mono text-sm">{String(latest.certification_id)}</p><p className="mt-3">Status: <strong>{String(latest.overall_status)}</strong></p><p className="mt-2 text-sm text-slate-600">Registry {String(latest.scenario_registry_version)} · Generated {String(latest.generated_at)}</p></section><section className="mt-8 overflow-x-auto rounded-2xl border border-slate-200 bg-white shadow-sm"><table className="min-w-full text-left text-sm"><thead className="bg-slate-50 text-xs uppercase text-slate-500"><tr>{["Scenario", "Status", "Attempts", "Recovery", "Audit", "Trace", "Result"].map((h) => <th key={h} className="px-4 py-3">{h}</th>)}</tr></thead><tbody>{scenarioResults.map((item, index) => <tr key={`${String(item.scenario_id)}-${index}`} className="border-t border-slate-100"><th className="px-4 py-3">{String(item.scenario_id)}</th><td className="px-4 py-3">{String(item.final_status)}</td><td className="px-4 py-3">{JSON.stringify(item.activity_attempts)}</td><td className="px-4 py-3">{String(item.recovery_boundary)}</td><td className="px-4 py-3">{String(item.audit_result)}</td><td className="px-4 py-3">{String(item.trace_result)}</td><td className="px-4 py-3">{item.passed ? "PASS" : "FAIL"}</td></tr>)}</tbody></table></section></> : <p className="mt-8 text-slate-600">No certification report has been generated.</p>}
    <section className="mt-8"><h2 className="text-xl font-bold text-ink">Registered scenarios</h2><p className="mt-2 text-sm text-slate-600">Registry version {String(catalog?.registry_version ?? "—")}</p><div className="mt-4 grid gap-3 md:grid-cols-2">{scenarioItems.map((item) => <article key={String(item.scenario_id)} className="rounded-xl border border-slate-200 bg-white p-4 text-sm"><strong>{String(item.scenario_id)}</strong><p className="mt-1 text-slate-600">{String(item.description)}</p></article>)}</div></section>
  </div></main>;
}
