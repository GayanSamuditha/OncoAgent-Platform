"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
export default function RunDetailsPage() { const { runId } = useParams<{ runId: string }>(); const [run, setRun] = useState<Record<string, unknown> | null>(null); useEffect(() => { fetch(`${apiBase}/api/v1/runs/${runId}`, { headers: { "X-Actor-Id": "researcher-console", "X-Actor-Role": "researcher" } }).then((r) => r.json()).then(setRun); }, [runId]); return <main className="min-h-screen px-5 py-8 sm:px-8 lg:px-12"><div className="mx-auto max-w-6xl"><Link className="text-sm font-semibold text-teal" href="/workflow">← Workflow Console</Link><h1 className="mt-8 text-3xl font-bold text-ink">Workflow run</h1>{run ? <pre className="mt-6 overflow-auto rounded-2xl bg-slate-950 p-6 text-xs text-slate-100">{JSON.stringify(run, null, 2)}</pre> : <p className="mt-6 text-slate-500">Loading run…</p>}</div></main>; }
