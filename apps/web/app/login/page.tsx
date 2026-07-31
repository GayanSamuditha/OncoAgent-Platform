"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch, explainError } from "../lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [userKey, setUserKey] = useState("researcher-console");
  const [message, setMessage] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    try { await apiFetch("/api/v1/auth/login", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ user_key: userKey }) }); const nextPath = new URLSearchParams(window.location.search).get("next"); router.replace(nextPath?.startsWith("/") ? nextPath : "/"); } catch (reason) { setMessage(explainError(reason)); }
  }

  return <main className="flex min-h-screen items-center justify-center bg-slate-50 px-5"><section className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-8 shadow-sm"><p className="text-xs font-semibold uppercase tracking-[0.2em] text-teal">OncoAgent Platform</p><h1 className="mt-3 text-2xl font-bold text-ink">Local development sign in</h1><p className="mt-3 text-sm text-slate-600">OIDC-compatible local identity simulation. This is not production authentication.</p><form onSubmit={submit} className="mt-6"><label htmlFor="user-key" className="block text-sm font-semibold">Development identity</label><select id="user-key" value={userKey} onChange={(event) => setUserKey(event.target.value)} className="mt-2 w-full rounded border border-slate-300 p-3"><option value="researcher-console">Researcher</option><option value="reviewer-console">Reviewer</option><option value="governance-console">Governance officer</option><option value="operator-console">Platform operator</option><option value="auditor-console">Auditor</option><option value="admin-console">Administrator</option></select><button type="submit" className="mt-5 w-full rounded bg-ink px-5 py-3 font-semibold text-white">Sign in</button></form>{message && <p role="alert" className="mt-4 rounded bg-red-50 p-3 text-sm text-red-800">{message}</p>}<p className="mt-6 text-xs text-slate-500">Synthetic Synthea data only. Not clinically validated.</p></section></main>;
}
