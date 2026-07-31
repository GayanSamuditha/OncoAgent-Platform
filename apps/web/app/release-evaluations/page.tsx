"use client";

import { useEffect, useState } from "react";
import { apiBase } from "../lib/api";

type Json = Record<string, unknown>;

function list(value: unknown): Json[] {
  return Array.isArray(value) ? value.filter((item): item is Json => typeof item === "object" && item !== null) : [];
}

export default function ReleaseEvaluationsPage() {
  const [evaluations, setEvaluations] = useState<Json[]>([]);
  const [selected, setSelected] = useState<Json | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch(`${apiBase}/api/v1/release-evaluations`, { credentials: "include", cache: "no-store" })
      .then((response) => response.ok ? response.json() : Promise.reject(new Error("unavailable")))
      .then((body: Json) => {
        const items = list(body.items);
        setEvaluations(items);
        if (items[0]?.id) {
          return fetch(`${apiBase}/api/v1/release-evaluations/${String(items[0].id)}`, { credentials: "include" })
            .then((response) => response.ok ? response.json() : Promise.reject(new Error("unavailable")))
            .then(setSelected);
        }
      })
      .catch(() => setError("Release evaluation data is unavailable."));
  }, []);

  const gates = list(selected?.gates);
  const metrics = list(selected?.metrics);
  const frameworks = selected?.framework_results as Json | undefined;
  const limitations = Array.isArray(selected?.limitations) ? selected.limitations : [];
  const blockingReasons = Array.isArray(selected?.blocking_reasons) ? selected.blocking_reasons : [];

  return (
    <main className="min-h-screen px-5 py-8 sm:px-8 lg:px-12">
      <div className="mx-auto max-w-6xl">
        <a className="font-semibold text-teal" href="/evaluations">← Evaluations</a>
        <p className="mt-8 text-sm font-semibold uppercase tracking-[0.18em] text-teal">Release evaluation</p>
        <h1 className="mt-2 text-3xl font-bold text-ink">Versioned AI release gates</h1>
        <div className="mt-5 rounded-2xl border border-amber-200 bg-amber-50 p-5 text-sm text-amber-950">
          <strong>Synthetic development evaluation.</strong> Not clinically validated or production performance. Missing measurements are explicitly blocked, not inferred.
        </div>
        {error && <p role="alert" className="mt-5 rounded bg-red-50 p-4 text-red-800">{error}</p>}
        <section className="mt-6 grid gap-4 md:grid-cols-3">
          <article className="rounded-2xl border border-slate-200 bg-white p-5"><p className="text-sm text-slate-500">Evaluations</p><p className="mt-2 text-2xl font-bold">{evaluations.length}</p></article>
          <article className="rounded-2xl border border-slate-200 bg-white p-5"><p className="text-sm text-slate-500">Latest decision</p><p className="mt-2 text-2xl font-bold">{String(selected?.decision ?? "—")}</p></article>
          <article className="rounded-2xl border border-slate-200 bg-white p-5"><p className="text-sm text-slate-500">Candidate / baseline</p><p className="mt-2 text-sm">{String((selected?.candidate as Json | undefined)?.candidate_version ?? "—")} / {String((selected?.candidate as Json | undefined)?.baseline_version ?? "—")}</p></article>
        </section>
        <section className="mt-8 overflow-x-auto rounded-2xl border border-slate-200 bg-white shadow-sm">
          <h2 className="p-5 text-xl font-bold">Blocking gates</h2>
          <table className="min-w-full text-left text-sm"><thead className="bg-slate-50"><tr><th className="px-4 py-3">Gate</th><th className="px-4 py-3">Value</th><th className="px-4 py-3">Threshold</th><th className="px-4 py-3">Status</th><th className="px-4 py-3">Reason</th></tr></thead><tbody>{gates.map((gate) => <tr key={String(gate.name)} className="border-t border-slate-100"><td className="px-4 py-3">{String(gate.name)}</td><td className="px-4 py-3">{gate.value == null ? "N/A" : String(gate.value)}</td><td className="px-4 py-3">{String(gate.threshold)}</td><td className="px-4 py-3">{gate.passed ? "PASS" : String(gate.status)}</td><td className="px-4 py-3">{String(gate.reason)}</td></tr>)}</tbody></table>
        </section>
        <section className="mt-8 overflow-x-auto rounded-2xl border border-slate-200 bg-white shadow-sm">
          <h2 className="p-5 text-xl font-bold">Baseline versus candidate metrics</h2>
          <table className="min-w-full text-left text-sm"><thead className="bg-slate-50"><tr><th className="px-4 py-3">Metric</th><th className="px-4 py-3">Candidate</th><th className="px-4 py-3">Baseline</th><th className="px-4 py-3">Delta</th></tr></thead><tbody>{metrics.map((metric) => <tr key={String(metric.name)} className="border-t border-slate-100"><td className="px-4 py-3">{String(metric.name)}</td><td className="px-4 py-3">{metric.value == null ? "N/A" : String(metric.value)}</td><td className="px-4 py-3">{metric.baseline_value == null ? "N/A" : String(metric.baseline_value)}</td><td className="px-4 py-3">{metric.delta == null ? "N/A" : String(metric.delta)}</td></tr>)}</tbody></table>
        </section>
        <section className="mt-8 grid gap-6 md:grid-cols-2">
          <article className="rounded-2xl border border-slate-200 bg-white p-5"><h2 className="text-xl font-bold">Framework results</h2><pre className="mt-3 overflow-auto text-xs text-slate-600">{JSON.stringify(frameworks ?? {}, null, 2)}</pre></article>
          <article className="rounded-2xl border border-slate-200 bg-white p-5"><h2 className="text-xl font-bold">Blocking reasons and limitations</h2><ul className="mt-3 list-disc space-y-2 pl-5 text-sm">{[...blockingReasons, ...limitations].map((item, index) => <li key={`${String(item)}-${index}`}>{String(item)}</li>)}</ul><p className="mt-4 text-xs text-slate-500">Supporting measured evidence:</p><nav className="mt-2 flex flex-wrap gap-3 text-sm font-semibold text-teal"><a href="/evaluations">Evaluations</a><a href="/resilience">Resilience</a><a href="/audit">Audit Explorer</a><a href="/observability">Observability</a></nav></article>
        </section>
      </div>
    </main>
  );
}
