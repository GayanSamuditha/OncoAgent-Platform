"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { apiBase } from "../lib/api";

type Json = Record<string, unknown>;

export default function SecurityPage() {
  const [policy, setPolicy] = useState<Json | null>(null);
  const [assessment, setAssessment] = useState<Json | null>(null);
  const [integrity, setIntegrity] = useState<Json | null>(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    Promise.all([
      fetch(`${apiBase}/api/v1/security/policy`, { credentials: "include", cache: "no-store" }).then((r) => { if (!r.ok) throw new Error("policy"); return r.json(); }),
      fetch(`${apiBase}/api/v1/security/assessments`, { credentials: "include", cache: "no-store" }).then((r) => { if (!r.ok) throw new Error("assessment"); return r.json(); }),
      fetch(`${apiBase}/api/v1/security/audit-integrity`, { credentials: "include", cache: "no-store" }).then((r) => { if (!r.ok) throw new Error("integrity"); return r.json(); }),
    ]).then(([policyResult, assessmentResult, integrityResult]) => {
      setPolicy(policyResult); setAssessment(assessmentResult); setIntegrity(integrityResult);
    }).catch(() => setError(true));
  }, []);
  const gates = (policy?.blocking_gates ?? {}) as Record<string, unknown>;
  const items = Array.isArray(assessment?.items) ? assessment.items as Json[] : [];
  return <main className="min-h-screen px-5 py-8 sm:px-8 lg:px-12"><div className="mx-auto max-w-6xl">
    <Link className="text-sm font-semibold text-teal" href="/">← Overview</Link>
    <p className="mt-8 text-sm font-semibold uppercase tracking-[0.18em] text-teal">Security &amp; Privacy</p>
    <h1 className="mt-2 text-3xl font-bold text-ink">Local security readiness</h1>
    <div className="mt-5 rounded-2xl border border-amber-200 bg-amber-50 p-5 text-sm text-amber-950"><strong>Development-only evidence.</strong> Synthetic data; not HIPAA or production security certification. Sensitive scanner output is intentionally omitted.</div>
    {error && <div role="alert" className="mt-6 rounded-2xl bg-red-50 p-5 text-red-800">Security evidence is unavailable or this account lacks security-readiness access.</div>}
    <section className="mt-8 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"><h2 className="text-xl font-bold">Policy gates</h2><div className="mt-4 grid gap-3 md:grid-cols-3">{Object.entries(gates).map(([name, value]) => <div className="rounded-xl bg-slate-50 p-4 text-sm" key={name}><p className="font-semibold">{name}</p><p className="mt-1 text-slate-600">Threshold: {JSON.stringify(value)}</p></div>)}</div></section>
    <section className="mt-8 grid gap-4 md:grid-cols-3"><div className="rounded-2xl border border-slate-200 bg-white p-5"><p className="text-sm text-slate-500">Audit integrity</p><p className="mt-2 text-xl font-bold">{String(integrity?.status ?? "—")}</p><p className="mt-2 text-sm text-slate-600">{String(integrity?.checked_records ?? 0)} records checked</p></div><div className="rounded-2xl border border-slate-200 bg-white p-5"><p className="text-sm text-slate-500">Legacy audit records</p><p className="mt-2 text-xl font-bold">{String(integrity?.legacy_records ?? "—")}</p><p className="mt-2 text-sm text-slate-600">Historical rows are never silently rewritten.</p></div><div className="rounded-2xl border border-slate-200 bg-white p-5"><p className="text-sm text-slate-500">Policy version</p><p className="mt-2 text-xl font-bold">{String(policy?.policy_version ?? "—")}</p><p className="mt-2 text-sm text-slate-600">Scanner outages remain not evaluable.</p></div></section>
    <section className="mt-8"><h2 className="text-xl font-bold">Assessment history</h2>{items.length === 0 ? <div className="mt-4 rounded-2xl border border-dashed border-slate-300 p-6 text-sm text-slate-500">No sanitized assessments have been recorded.</div> : <div className="mt-4 overflow-x-auto rounded-2xl border border-slate-200 bg-white"><table className="min-w-full text-left text-sm"><thead className="bg-slate-50 text-xs uppercase text-slate-500"><tr><th className="px-4 py-3">Assessment</th><th className="px-4 py-3">Status</th><th className="px-4 py-3">Created</th></tr></thead><tbody>{items.map((item) => <tr className="border-t border-slate-100" key={String(item.assessment_id)}><th className="px-4 py-3 font-medium">{String(item.assessment_id)}</th><td className="px-4 py-3">{String(item.status)}</td><td className="px-4 py-3">{String(item.created_at ?? "—")}</td></tr>)}</tbody></table></div>}</section>
  </div></main>;
}
