"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

type Json = Record<string, unknown>;
const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

async function read(path: string): Promise<Json> {
  const response = await fetch(`${apiBase}${path}`, { cache: "no-store", headers: { "X-Actor-Id": "observability-console", "X-Actor-Role": "admin" } });
  if (!response.ok) throw new Error("unavailable");
  return response.json() as Promise<Json>;
}

export default function ObservabilityPage() {
  const [status, setStatus] = useState<Json | null>(null);
  const [services, setServices] = useState<Json | null>(null);
  const [summary, setSummary] = useState<Json | null>(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    Promise.all([read("/api/v1/observability/status"), read("/api/v1/observability/services"), read("/api/v1/observability/metrics-summary")])
      .then(([s, svc, m]) => { setStatus(s); setServices(svc); setSummary(m); })
      .catch(() => setError(true));
  }, []);
  const serviceItems = (services?.services as Json[] | undefined) ?? [];
  return <main className="min-h-screen px-5 py-8 sm:px-8 lg:px-12"><div className="mx-auto max-w-6xl">
    <Link className="text-sm font-semibold text-teal" href="/">← Overview</Link>
    <p className="mt-8 text-sm font-semibold uppercase tracking-[0.18em] text-teal">Observability</p>
    <h1 className="mt-2 text-3xl font-bold text-ink">Local execution telemetry</h1>
    <p className="mt-3 text-slate-600">Operational traces, bounded metrics, and redacted logs. Audit tables remain the authoritative institutional history.</p>
    <div className="mt-5 rounded-2xl border border-amber-200 bg-amber-50 p-5 text-sm text-amber-950">Synthetic Synthea data only. Not clinically validated. Development-only local observability; no secrets, prompts, raw FHIR, or hidden reasoning are displayed.</div>
    {error && <p role="alert" className="mt-5 rounded bg-red-50 p-4 text-red-800">Observability inspection data is unavailable.</p>}
    <div className="mt-6 grid gap-4 md:grid-cols-3"><article className="rounded-2xl border border-slate-200 bg-white p-5"><h2 className="font-semibold">Telemetry</h2><p className="mt-2 text-2xl font-bold">{status?.enabled ? "Enabled" : "Disabled"}</p><p className="mt-2 text-sm text-slate-600">{String(status?.exporter_endpoint ?? "—")}</p></article><article className="rounded-2xl border border-slate-200 bg-white p-5"><h2 className="font-semibold">Workflow runs</h2><p className="mt-2 text-2xl font-bold">{String(summary?.workflow_runs ?? "—")}</p></article><article className="rounded-2xl border border-slate-200 bg-white p-5"><h2 className="font-semibold">MCP requests</h2><p className="mt-2 text-2xl font-bold">{String(summary?.mcp_requests ?? "—")}</p></article></div>
    <section className="mt-8 rounded-2xl border border-slate-200 bg-white p-6"><h2 className="text-xl font-bold">Service boundaries</h2><div className="mt-4 grid gap-3 md:grid-cols-2">{serviceItems.map((item) => <div key={String(item.service)} className="rounded-xl bg-slate-50 p-4"><div className="flex justify-between"><span className="font-semibold">{String(item.service)}</span><span className="text-sm text-slate-600">{String(item.status)}</span></div><p className="mt-1 text-sm text-slate-600">{String(item.transport ?? "local")}</p></div>)}</div></section>
    <section className="mt-8 rounded-2xl border border-slate-200 bg-white p-6"><h2 className="text-xl font-bold">Local tools</h2><p className="mt-2 text-sm text-slate-600">Prometheus: <a className="text-teal underline" href="http://127.0.0.1:9090" target="_blank" rel="noreferrer">127.0.0.1:9090</a> · Grafana: <a className="text-teal underline" href="http://127.0.0.1:3001" target="_blank" rel="noreferrer">127.0.0.1:3001</a> · Metrics: <a className="text-teal underline" href={`${apiBase}/metrics`} target="_blank" rel="noreferrer">API /metrics</a></p></section>
  </div></main>;
}
