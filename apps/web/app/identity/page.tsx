"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { apiBase } from "../lib/api";

export default function IdentityPage() {
  const [body, setBody] = useState<Record<string, unknown> | null>(null);
  useEffect(() => { fetch(`${apiBase}/api/v1/identity/users`, { credentials: "include" }).then((response) => response.json()).then(setBody); }, []);
  return <main className="min-h-screen px-5 py-8 sm:px-8 lg:px-12"><div className="mx-auto max-w-6xl"><Link href="/">← Overview</Link><h1 className="mt-8 text-3xl font-bold text-ink">Identity and access</h1><p className="mt-3 text-slate-600">Local-development users, server-side roles, persisted dataset grants, and reviewer assignments.</p><div className="mt-6 rounded-2xl border border-amber-200 bg-amber-50 p-5 text-sm text-amber-950">Development identity simulation only. Backend authorization is authoritative; hidden navigation is not a security control.</div>{body ? <pre className="mt-6 overflow-auto rounded-2xl bg-slate-950 p-6 text-xs text-slate-100">{JSON.stringify(body, null, 2)}</pre> : <p className="mt-6 text-slate-500">Loading identity data…</p>}</div></main>;
}
