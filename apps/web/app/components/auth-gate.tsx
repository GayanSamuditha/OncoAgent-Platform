"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ApiError, apiFetch, explainError, Role, User } from "../lib/api";

export default function AuthGate({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [state, setState] = useState<"loading" | "authenticated" | "denied">("loading");
  const [user, setUser] = useState<User | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (pathname === "/login") {
      return;
    }
    apiFetch<User>("/api/v1/auth/me").then((body) => { setUser(body); setState("authenticated"); }).catch((reason) => {
      if (reason instanceof ApiError && reason.status === 401) router.replace(`/login?next=${encodeURIComponent(pathname)}`);
      else { setError(explainError(reason)); setState("denied"); }
    });
  }, [pathname, router]);

  if (pathname === "/login") return <>{children}</>;
  if (state === "loading") return <main className="p-8 text-slate-600">Checking authenticated session…</main>;
  if (state === "denied") return <main className="mx-auto max-w-xl p-8"><div className="rounded-2xl border border-red-200 bg-red-50 p-6 text-red-900"><h1 className="text-lg font-bold">OncoAgent is temporarily unavailable</h1><p className="mt-2 text-sm">{error || "Access denied."}</p><Link href="/login" className="mt-4 inline-block font-semibold underline">Return to sign in</Link></div></main>;
  const role = user?.role;
  const research = [{ label: "Research Workspace", href: "/workflow", roles: ["researcher", "administrator"] }, { label: "My Runs", href: "/runs", roles: ["researcher", "administrator"] }, { label: "Reviews", href: "/approvals", roles: ["reviewer", "administrator"] }, { label: "Evidence", href: "/evidence", roles: ["researcher", "reviewer", "administrator"] }];
  const operations = [{ label: "Agent Catalog", href: "/agent-catalog", roles: ["administrator", "platform_operator"] }, { label: "Evaluations", href: "/evaluations", roles: ["administrator", "governance_officer"] }, { label: "Release Gates", href: "/release-evaluations", roles: ["administrator", "governance_officer"] }, { label: "Performance", href: "/performance", roles: ["administrator", "platform_operator"] }, { label: "Resilience", href: "/resilience", roles: ["administrator", "platform_operator"] }, { label: "Observability", href: "/observability", roles: ["administrator", "platform_operator"] }];
  const governance = [{ label: "Audit", href: "/audit", roles: ["administrator", "auditor", "governance_officer"] }, { label: "Identity", href: "/identity", roles: ["administrator", "governance_officer"] }, { label: "Security & Privacy", href: "/security", roles: ["administrator", "governance_officer"] }];
  const allowed = (item: { roles: string[] }) => item.roles.includes(role ?? "");
  const navGroup = (title: string, items: typeof research) => <div><p className="mb-2 text-[10px] font-bold uppercase tracking-[0.18em] text-slate-400">{title}</p><div className="space-y-1">{items.filter(allowed).map((item) => <Link key={item.href} href={item.href} className={`block rounded-lg px-3 py-2 text-sm ${pathname === item.href || pathname.startsWith(`${item.href}/`) ? "bg-teal-50 font-semibold text-teal-900" : "text-slate-600 hover:bg-slate-100"}`}>{item.label}</Link>)}</div></div>;
  return <div className="min-h-screen bg-slate-50"><header className="border-b border-slate-200 bg-white"><div className="mx-auto flex max-w-[1500px] items-center justify-between gap-4 px-5 py-3"><Link href="/" className="font-bold tracking-tight text-ink">OncoAgent <span className="font-normal text-slate-500">/ synthetic research</span></Link><div className="flex items-center gap-4 text-xs text-slate-600"><Link href="/demo" className="font-semibold text-teal">Demo Control Center</Link><span>{user?.display_name ?? "Authenticated user"} · {user?.role ?? "role"}</span><button onClick={() => { apiFetch("/api/v1/auth/logout", { method: "POST" }).finally(() => router.replace("/login")); }} className="font-semibold text-teal">Log out</button></div></div></header><div className="mx-auto flex max-w-[1500px]"><aside className="hidden w-56 shrink-0 border-r border-slate-200 bg-white px-4 py-6 lg:block"><nav className="space-y-7" aria-label="Application navigation"><Link href="/" className="mb-5 block rounded-lg px-3 py-2 text-sm font-semibold text-slate-700">Overview</Link>{navGroup("Research", research)}{navGroup("Operations", operations)}{navGroup("Governance", governance)}</nav></aside><div className="min-w-0 flex-1">{children}</div></div></div>;
}
