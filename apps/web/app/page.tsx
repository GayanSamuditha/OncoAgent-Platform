"use client";

import { useEffect, useState } from "react";

type Health = { status: "ok"; service: string; version: string };
type Readiness = {
  status: "ready" | "not_ready";
  database: "available" | "unavailable";
};
type PlatformInfo = {
  platform_name: string;
  application_version: string;
  data_policy: string;
  clinical_validation_status: string;
  capabilities: { implemented: string[]; planned: string[] };
};
type LocalRuntime = { model: string; status?: { healthy?: boolean; installed?: boolean; resolved_model_digest?: string } };

const navigation = ["Overview", "Agent Catalog", "Workflow Console", "Approvals", "Evaluations", "Observability", "Identity & Access", "Deployments", "Audit Explorer"];
const navigationLinks: Record<string, string> = { "Overview": "/", "Agent Catalog": "/agent-catalog", "Workflow Console": "/workflow", "Approvals": "/approvals", "Evaluations": "/evaluations", "Observability": "/observability", "Identity & Access": "/identity", "Deployments": "#planned", "Audit Explorer": "/audit" };
const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

async function readJson<T>(path: string): Promise<T> {
  const response = await fetch(`${apiBase}${path}`, { cache: "no-store" });
  if (!response.ok) throw new Error(`${path} returned ${response.status}`);
  return response.json() as Promise<T>;
}

function StatusCard({ label, state, detail }: { label: string; state: string; detail: string }) {
  const healthy = state === "Operational" || state === "Ready";
  return (
    <article className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold text-ink">{label}</h3>
        <span className={`rounded-full px-3 py-1 text-xs font-semibold ${healthy ? "bg-emerald-100 text-emerald-800" : "bg-amber-100 text-amber-800"}`}>
          {state}
        </span>
      </div>
      <p className="mt-3 text-sm text-slate-600">{detail}</p>
    </article>
  );
}

export default function OverviewPage() {
  const [health, setHealth] = useState<Health | null>(null);
  const [readiness, setReadiness] = useState<Readiness | null>(null);
  const [info, setInfo] = useState<PlatformInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [backendError, setBackendError] = useState(false);
  const [localRuntime, setLocalRuntime] = useState<LocalRuntime | null>(null);

  useEffect(() => {
    Promise.allSettled([readJson<Health>("/health"), readJson<Readiness>("/ready"), readJson<PlatformInfo>("/api/v1/platform/info"), readJson<LocalRuntime>("/api/v1/models/local-runtime")])
      .then(([healthResult, readinessResult, infoResult, localResult]) => {
        if (healthResult.status === "fulfilled") setHealth(healthResult.value);
        if (readinessResult.status === "fulfilled") setReadiness(readinessResult.value);
        if (infoResult.status === "fulfilled") setInfo(infoResult.value);
        if (localResult.status === "fulfilled") setLocalRuntime(localResult.value);
        setBackendError(healthResult.status === "rejected" && infoResult.status === "rejected");
      })
      .finally(() => setLoading(false));
  }, []);

  const capabilities = info?.capabilities ?? { implemented: [], planned: [] };

  return (
    <main className="min-h-screen lg:flex">
      <aside className="border-b border-slate-200 bg-ink px-6 py-6 text-white lg:min-h-screen lg:w-72 lg:border-b-0 lg:px-7">
        <div className="mb-10">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-teal-200">Platform console</p>
          <h1 className="mt-3 text-2xl font-bold">OncoAgent</h1>
          <p className="mt-1 text-sm text-slate-300">Governed AI for synthetic oncology research</p>
        </div>
        <nav aria-label="Primary navigation">
          <ul className="space-y-2">
            {navigation.map((item, index) => (
              <li key={item}>
                <a href={navigationLinks[item]} className={`block rounded-xl px-4 py-3 text-sm ${index === 0 ? "bg-white/15 font-semibold text-white" : "text-slate-300 hover:bg-white/10 hover:text-white"}`}>
                  {item}
                  {item === "Deployments" && <span className="float-right text-xs text-slate-400">Planned</span>}
                </a>
              </li>
            ))}
          </ul>
        </nav>
      </aside>

      <section id="overview" className="w-full px-5 py-8 sm:px-8 lg:px-12 lg:py-12">
        <div className="mx-auto max-w-6xl">
          <div className="flex flex-col justify-between gap-4 md:flex-row md:items-end">
            <div>
              <p className="text-sm font-semibold uppercase tracking-[0.18em] text-teal">Overview</p>
              <h2 className="mt-2 text-3xl font-bold tracking-tight text-ink sm:text-4xl">A governed foundation for agentic oncology research</h2>
              <p className="mt-4 max-w-3xl text-slate-600">Phase 0 establishes the platform shell, service health, database readiness, and clear boundaries for future workflow capabilities.</p>
            </div>
            <span className="rounded-full bg-white px-4 py-2 text-sm font-semibold text-slate-600 shadow-sm">v{info?.application_version ?? health?.version ?? "—"}</span>
          </div>

          <div className="mt-8 grid gap-4 md:grid-cols-2">
            {loading ? <div className="rounded-2xl bg-white p-5 text-sm text-slate-500">Checking platform services…</div> : <StatusCard label="Backend API" state={backendError ? "Unavailable" : health ? "Operational" : "Unavailable"} detail={backendError ? "Start FastAPI on port 8000 to connect this console." : "FastAPI health endpoint is responding."} />}
            <StatusCard label="PostgreSQL readiness" state={readiness?.status === "ready" ? "Ready" : "Unavailable"} detail={readiness?.status === "ready" ? "Database connectivity is available." : "The API cannot currently verify PostgreSQL readiness."} />
            <StatusCard label="Local planner" state={localRuntime?.status?.healthy && localRuntime.status.installed ? "Operational" : "Fallback available"} detail={localRuntime ? `${localRuntime.model} · ${localRuntime.status?.resolved_model_digest ? "installed" : "not loaded"}. Deterministic fallback remains enabled.` : "Checking Ollama status…"} />
          </div>

          <div className="mt-6 rounded-2xl border border-amber-200 bg-amber-50 p-5 text-sm text-amber-950">
            <strong>Synthetic-data notice:</strong> {info?.data_policy ?? "Synthetic Synthea data only."} This platform is <strong>not clinically validated</strong> and must not be used for clinical decisions.
          </div>

          <div className="mt-10 grid gap-6 lg:grid-cols-2">
            <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
              <h3 className="text-lg font-bold text-ink">Implemented capabilities</h3>
              <ul className="mt-4 space-y-3 text-sm text-slate-600">
                {capabilities.implemented.map((capability) => <li key={capability} className="flex gap-3"><span className="text-teal">●</span>{capability}</li>)}
              </ul>
            </section>
            <section id="planned" className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
              <h3 className="text-lg font-bold text-ink">Planned capabilities</h3>
              <ul className="mt-4 space-y-3 text-sm text-slate-600">
                {capabilities.planned.map((capability) => <li key={capability} className="flex gap-3"><span className="text-slate-400">○</span>{capability}</li>)}
              </ul>
            </section>
          </div>
        </div>
      </section>
    </main>
  );
}
