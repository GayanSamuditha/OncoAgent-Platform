"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export default function AuthGate({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [state, setState] = useState<"loading" | "authenticated" | "denied">("loading");
  const [user, setUser] = useState<{ display_name?: string; role?: string } | null>(null);

  useEffect(() => {
    if (pathname === "/login") {
      return;
    }
    fetch(`${apiBase}/api/v1/auth/me`, { credentials: "include", cache: "no-store" })
      .then((response) => {
        if (response.status === 401) {
          router.replace(`/login?next=${encodeURIComponent(pathname)}`);
          return "denied";
        }
        if (response.ok) { response.json().then(setUser).catch(() => undefined); return "authenticated"; }
        return "denied";
      })
      .then((next) => setState(next as "authenticated" | "denied"))
      .catch(() => setState("denied"));
  }, [pathname, router]);

  if (pathname === "/login") return <>{children}</>;
  if (state === "loading") return <main className="p-8 text-slate-600">Checking authenticated session…</main>;
  if (state === "denied") return <main className="p-8 text-red-800">Access denied or backend unavailable.</main>;
  return <><div className="flex items-center justify-end gap-3 border-b border-slate-200 bg-white px-5 py-2 text-xs text-slate-600"><span>{user?.display_name ?? "Authenticated user"} · {user?.role ?? "role"}</span><button onClick={() => { fetch(`${apiBase}/api/v1/auth/logout`, { method: "POST", credentials: "include" }).finally(() => router.replace("/login")); }} className="font-semibold text-teal">Log out</button></div>{children}</>;
}
